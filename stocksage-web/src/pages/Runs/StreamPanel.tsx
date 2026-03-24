import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Card, Tag, Timeline, Typography, Spin } from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  SyncOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import InteractionDialog from './InteractionDialog';

const { Text, Paragraph } = Typography;

// ── Types ────────────────────────────────────────────────────────────────────

interface StreamEvent {
  event: string;
  skill_name?: string;
  phase?: string;
  payload?: string;
  item_id?: string;
  timestamp?: string;
  error?: string;
  summary?: string;
}

interface SkillState {
  name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  chunks: string; // accumulated text
}

interface StreamPanelProps {
  runId: string;
  onCompleted?: () => void;
}

interface PendingInteraction {
  prompt: string;
  options: string[];
  timeout: number;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const phaseLabels: Record<string, string> = {
  init: '初始化',
  memory_recall: '记忆召回',
  execution: '执行中',
  completed: '已完成',
};

const skillStatusIcons: Record<string, React.ReactNode> = {
  pending: <ClockCircleOutlined style={{ color: '#d9d9d9' }} />,
  running: <SyncOutlined spin style={{ color: '#1677ff' }} />,
  completed: <CheckCircleOutlined style={{ color: '#52c41a' }} />,
  failed: <CloseCircleOutlined style={{ color: '#ff4d4f' }} />,
};

// ── Component ────────────────────────────────────────────────────────────────

const StreamPanel: React.FC<StreamPanelProps> = ({ runId, onCompleted }) => {
  const [connected, setConnected] = useState(false);
  const [phase, setPhase] = useState('init');
  const [skills, setSkills] = useState<Map<string, SkillState>>(new Map());
  const [logs, setLogs] = useState<StreamEvent[]>([]);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [interaction, setInteraction] = useState<PendingInteraction | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs, skills]);

  const handleEvent = useCallback((event: StreamEvent) => {
    setLogs((prev) => [...prev.slice(-200), event]); // keep last 200 log entries

    switch (event.event) {
      case 'phase_changed':
        setPhase(event.phase || '');
        break;

      case 'skill_started':
        if (event.skill_name) {
          setSkills((prev) => {
            const next = new Map(prev);
            next.set(event.skill_name!, {
              name: event.skill_name!,
              status: 'running',
              chunks: '',
            });
            return next;
          });
        }
        break;

      case 'skill_chunk':
        if (event.skill_name && event.payload) {
          setSkills((prev) => {
            const next = new Map(prev);
            const existing = next.get(event.skill_name!);
            if (existing) {
              next.set(event.skill_name!, {
                ...existing,
                chunks: existing.chunks + event.payload!,
              });
            }
            return next;
          });
        }
        break;

      case 'skill_paragraph':
        if (event.skill_name && event.payload) {
          setSkills((prev) => {
            const next = new Map(prev);
            const existing = next.get(event.skill_name!);
            if (existing) {
              next.set(event.skill_name!, {
                ...existing,
                chunks: event.payload!,
              });
            }
            return next;
          });
        }
        break;

      case 'skill_completed':
        if (event.skill_name) {
          setSkills((prev) => {
            const next = new Map(prev);
            const existing = next.get(event.skill_name!);
            next.set(event.skill_name!, {
              name: event.skill_name!,
              status: 'completed',
              chunks: existing?.chunks || '',
            });
            return next;
          });
        }
        break;

      case 'skill_failed':
        if (event.skill_name) {
          setSkills((prev) => {
            const next = new Map(prev);
            next.set(event.skill_name!, {
              name: event.skill_name!,
              status: 'failed',
              chunks: event.error || '',
            });
            return next;
          });
        }
        break;

      case 'run_completed':
        setDone(true);
        setPhase('completed');
        onCompleted?.();
        break;

      case 'run_failed':
        setDone(true);
        setError(event.error || '执行失败');
        break;

      case 'interaction_required':
        setInteraction({
          prompt: event.payload || '请确认',
          options: (event as any).options || [],
          timeout: (event as any).timeout || 120,
        });
        break;

      default:
        break;
    }
  }, [onCompleted]);

  // SSE connection
  useEffect(() => {
    if (!runId || done) return;

    const es = new EventSource(`/api/runs/${runId}/stream`);
    esRef.current = es;

    es.onopen = () => setConnected(true);

    // Listen for all event types
    const eventTypes = [
      'run_started', 'phase_changed', 'skill_started', 'skill_chunk',
      'skill_paragraph', 'skill_completed', 'skill_failed',
      'interaction_required', 'run_completed', 'run_failed', 'heartbeat',
    ];

    for (const type of eventTypes) {
      es.addEventListener(type, (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          handleEvent({ event: type, ...data });
        } catch {
          // ignore parse errors
        }
      });
    }

    es.onerror = () => {
      setConnected(false);
      // EventSource will auto-reconnect
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [runId, done, handleEvent]);

  const skillEntries = Array.from(skills.values());
  const runningCount = skillEntries.filter((s) => s.status === 'running').length;
  const completedCount = skillEntries.filter((s) => s.status === 'completed').length;

  return (
    <Card
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <ThunderboltOutlined />
          <span>实时执行流</span>
          <Tag color={connected ? 'green' : 'red'}>
            {connected ? 'SSE 已连接' : 'SSE 未连接'}
          </Tag>
          {phase && (
            <Tag color="blue">{phaseLabels[phase] || phase}</Tag>
          )}
          {!done && (
            <Text type="secondary" style={{ fontSize: 12, marginLeft: 'auto' }}>
              {runningCount > 0 ? `${runningCount} 个 Skill 执行中` : ''}{' '}
              {completedCount > 0 ? `${completedCount} 个已完成` : ''}
            </Text>
          )}
        </div>
      }
      style={{ marginBottom: 16 }}
    >
      {/* Skill execution cards */}
      {skillEntries.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
          {skillEntries.map((skill) => (
            <Card
              key={skill.name}
              size="small"
              style={{
                borderLeft: `3px solid ${
                  skill.status === 'running' ? '#1677ff' :
                  skill.status === 'completed' ? '#52c41a' :
                  skill.status === 'failed' ? '#ff4d4f' : '#d9d9d9'
                }`,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                {skillStatusIcons[skill.status]}
                <Text strong style={{ fontSize: 13 }}>{skill.name}</Text>
                <Tag style={{ marginLeft: 'auto' }}>
                  {skill.status === 'running' ? '执行中...' :
                   skill.status === 'completed' ? '已完成' :
                   skill.status === 'failed' ? '失败' : '等待中'}
                </Tag>
              </div>
              {skill.chunks && skill.status === 'running' && (
                <pre style={{
                  maxHeight: 120,
                  overflow: 'auto',
                  fontSize: 11,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  background: '#f5f5f5',
                  padding: 6,
                  margin: '4px 0 0 0',
                  borderRadius: 4,
                }}>
                  {skill.chunks.slice(-500)}
                  <span className="cursor-blink">|</span>
                </pre>
              )}
            </Card>
          ))}
        </div>
      )}

      {/* Loading state when no skills yet */}
      {skillEntries.length === 0 && !done && (
        <div style={{ textAlign: 'center', padding: 24 }}>
          <Spin indicator={<LoadingOutlined />} />
          <div style={{ marginTop: 8 }}>
            <Text type="secondary">等待工作流启动...</Text>
          </div>
        </div>
      )}

      {/* Error display */}
      {error && (
        <Card size="small" style={{ borderColor: '#ff4d4f', marginBottom: 8 }}>
          <Text type="danger">{error}</Text>
        </Card>
      )}

      {/* Completion summary */}
      {done && !error && (
        <Card size="small" style={{ borderColor: '#52c41a', background: '#f6ffed' }}>
          <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 8 }} />
          <Text>工作流执行完成，共完成 {completedCount} 个 Skill</Text>
        </Card>
      )}

      {/* Interaction dialog */}
      {interaction && (
        <InteractionDialog
          runId={runId}
          prompt={interaction.prompt}
          options={interaction.options}
          timeout={interaction.timeout}
          onDismiss={() => setInteraction(null)}
        />
      )}

      <div ref={bottomRef} />
    </Card>
  );
};

export default StreamPanel;
