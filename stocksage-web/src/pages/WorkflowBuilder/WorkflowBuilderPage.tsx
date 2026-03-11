import React, { useState, useCallback, useRef, useMemo, type DragEvent } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  type Node,
  type Edge,
  type Connection,
  type NodeTypes,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  Layout,
  Typography,
  Button,
  Card,
  Collapse,
  Tag,
  Space,
  Input,
  Select,
  Form,
  Divider,
  Modal,
  List,
  message,
  Tooltip,
} from 'antd';
import {
  SaveOutlined,
  CheckCircleOutlined,
  FileOutlined,
  DatabaseOutlined,
  LineChartOutlined,
  TeamOutlined,
  ExperimentOutlined,
  AimOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import { workflowApi } from '../../api/endpoints';
import type {
  WorkflowDefinition,
  NodeDef,
  EdgeDef,
  WorkflowTemplate,
  Workflow,
} from '../../types';

const { Header, Sider, Content } = Layout;
const { Title, Text } = Typography;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SKILL_CATEGORIES = [
  { label: 'Data', skills: ['data_collector'] },
  { label: 'Analyst', skills: [
    'technical_analyst', 'fundamental_analyst', 'risk_analyst',
    'sentiment_analyst', 'news_analyst', 'fund_flow_analyst',
    'valuation_analyst', 'industry_analyst', 'macro_analyst',
    'conflict_aggregator',
  ]},
  { label: 'Debate', skills: [
    'bull_advocate', 'bear_advocate',
    'debate_r1_bull_challenge', 'debate_r1_bear_response',
    'debate_r2_bull_revise', 'debate_r2_bear_revise',
    'debate_r3_bull', 'debate_r3_bear',
  ]},
  { label: 'Expert', skills: [
    'blind_spot_detector', 'consensus_analyzer', 'decision_tree_builder',
    'quality_checker', 'evidence_validator',
    'blind_spot_researcher',
  ]},
  { label: 'Decision', skills: ['panel_coordinator', 'judge', 'report_writer', 'portfolio_advisor'] },
];

const CATEGORY_FOR_SKILL: Record<string, string> = {};
SKILL_CATEGORIES.forEach((cat) => {
  cat.skills.forEach((s) => {
    CATEGORY_FOR_SKILL[s] = cat.label;
  });
});

const EDGE_TYPES: EdgeDef['type'][] = ['serial', 'fan_out', 'fan_in', 'conditional'];

const CATEGORY_COLORS: Record<string, string> = {
  Data: '#1677ff',
  Analyst: '#52c41a',
  Debate: '#fa8c16',
  Expert: '#722ed1',
  Decision: '#eb2f96',
};

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  Data: <DatabaseOutlined />,
  Analyst: <LineChartOutlined />,
  Debate: <TeamOutlined />,
  Expert: <ExperimentOutlined />,
  Decision: <AimOutlined />,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let nodeIdCounter = 0;
function nextNodeId(): string {
  nodeIdCounter += 1;
  return `node_${nodeIdCounter}`;
}

/** Pretty-print a skill key: "stock_data" -> "Stock Data" */
function formatSkillName(skill: string): string {
  return skill
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

// ---------------------------------------------------------------------------
// SkillNode  -- custom node rendered on the canvas
// ---------------------------------------------------------------------------

interface SkillNodeData {
  skill: string;
  category: string;
  config: Record<string, unknown>;
  [key: string]: unknown;
}

type SkillNodeType = Node<SkillNodeData, 'skillNode'>;

interface SkillEdgeData {
  edgeType: string;
  [key: string]: unknown;
}

type SkillEdgeType = Edge<SkillEdgeData>;

function SkillNode({ data, selected }: { data: SkillNodeData; selected: boolean }) {
  const category = data.category || CATEGORY_FOR_SKILL[data.skill] || 'Data';
  const color = CATEGORY_COLORS[category] || '#1677ff';

  return (
    <div
      style={{
        background: '#fff',
        border: `2px solid ${selected ? color : '#d9d9d9'}`,
        borderRadius: 8,
        padding: '8px 14px',
        minWidth: 160,
        boxShadow: selected ? `0 0 0 2px ${color}33` : '0 1px 4px rgba(0,0,0,0.08)',
        transition: 'border-color 0.2s, box-shadow 0.2s',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: color }} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <span style={{ color, fontSize: 16 }}>{CATEGORY_ICONS[category]}</span>
        <Text strong style={{ fontSize: 13 }}>
          {formatSkillName(data.skill)}
        </Text>
      </div>

      <Tag color={color} style={{ margin: 0, fontSize: 11 }}>
        {category}
      </Tag>

      <Handle type="source" position={Position.Bottom} style={{ background: color }} />
    </div>
  );
}

const NODE_TYPES: NodeTypes = {
  skillNode: SkillNode as any,
};

// ---------------------------------------------------------------------------
// SkillPanel  -- left sidebar with draggable skill items
// ---------------------------------------------------------------------------

function SkillPanel() {
  const onDragStart = (event: DragEvent<HTMLDivElement>, skill: string) => {
    event.dataTransfer.setData('application/reactflow', skill);
    event.dataTransfer.effectAllowed = 'move';
  };

  const collapseItems = SKILL_CATEGORIES.map((cat) => ({
    key: cat.label,
    label: (
      <Space>
        {CATEGORY_ICONS[cat.label]}
        <span>{cat.label}</span>
      </Space>
    ),
    children: (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {cat.skills.map((skill) => (
          <div
            key={skill}
            draggable
            onDragStart={(e) => onDragStart(e, skill)}
            style={{
              padding: '6px 10px',
              background: '#fafafa',
              border: '1px solid #f0f0f0',
              borderRadius: 6,
              cursor: 'grab',
              fontSize: 13,
              transition: 'background 0.15s',
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLDivElement).style.background = '#e6f4ff';
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLDivElement).style.background = '#fafafa';
            }}
          >
            {formatSkillName(skill)}
          </div>
        ))}
      </div>
    ),
  }));

  return (
    <div style={{ padding: 12 }}>
      <Title level={5} style={{ marginTop: 0, marginBottom: 12 }}>
        Skills
      </Title>
      <Collapse
        defaultActiveKey={SKILL_CATEGORIES.map((c) => c.label)}
        size="small"
        items={collapseItems}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// PropertiesPanel  -- right sidebar for selected node / edge
// ---------------------------------------------------------------------------

interface PropertiesPanelProps {
  selectedNode: SkillNodeType | null;
  selectedEdge: SkillEdgeType | null;
  onUpdateNodeData: (nodeId: string, patch: Partial<SkillNodeData>) => void;
  onUpdateEdgeType: (edgeId: string, edgeType: EdgeDef['type']) => void;
  onDeleteNode: (nodeId: string) => void;
  onDeleteEdge: (edgeId: string) => void;
}

function PropertiesPanel({
  selectedNode,
  selectedEdge,
  onUpdateNodeData,
  onUpdateEdgeType,
  onDeleteNode,
  onDeleteEdge,
}: PropertiesPanelProps) {
  if (!selectedNode && !selectedEdge) {
    return (
      <div style={{ padding: 16, color: '#999', textAlign: 'center', marginTop: 40 }}>
        <FileOutlined style={{ fontSize: 32, marginBottom: 8 }} />
        <br />
        Select a node or edge to view its properties.
      </div>
    );
  }

  if (selectedEdge) {
    const edgeType = selectedEdge.data?.edgeType ?? 'serial';
    return (
      <div style={{ padding: 12 }}>
        <Title level={5} style={{ marginTop: 0 }}>
          Edge Properties
        </Title>
        <Form layout="vertical" size="small">
          <Form.Item label="From">
            <Input value={selectedEdge.source} disabled />
          </Form.Item>
          <Form.Item label="To">
            <Input value={selectedEdge.target} disabled />
          </Form.Item>
          <Form.Item label="Type">
            <Select
              value={edgeType}
              onChange={(val) => onUpdateEdgeType(selectedEdge.id, val as EdgeDef['type'])}
              options={EDGE_TYPES.map((t) => ({ label: t, value: t }))}
              style={{ width: '100%' }}
            />
          </Form.Item>
          <Button danger icon={<DeleteOutlined />} block onClick={() => onDeleteEdge(selectedEdge.id)}>
            Delete Edge
          </Button>
        </Form>
      </div>
    );
  }

  if (selectedNode) {
    const { skill, category, config } = selectedNode.data;
    const configStr = JSON.stringify(config ?? {}, null, 2);

    return (
      <div style={{ padding: 12 }}>
        <Title level={5} style={{ marginTop: 0 }}>
          Node Properties
        </Title>
        <Form layout="vertical" size="small">
          <Form.Item label="ID">
            <Input value={selectedNode.id} disabled />
          </Form.Item>
          <Form.Item label="Skill">
            <Input value={formatSkillName(skill)} disabled />
          </Form.Item>
          <Form.Item label="Category">
            <Tag color={CATEGORY_COLORS[category] || '#1677ff'}>{category}</Tag>
          </Form.Item>
          <Form.Item label="Config (JSON)">
            <Input.TextArea
              rows={6}
              value={configStr}
              onChange={(e) => {
                try {
                  const parsed = JSON.parse(e.target.value);
                  onUpdateNodeData(selectedNode.id, { config: parsed });
                } catch {
                  // Invalid JSON -- ignore until valid
                }
              }}
            />
          </Form.Item>
          <Button danger icon={<DeleteOutlined />} block onClick={() => onDeleteNode(selectedNode.id)}>
            Delete Node
          </Button>
        </Form>
      </div>
    );
  }

  return null;
}

// ---------------------------------------------------------------------------
// Serialization helpers
// ---------------------------------------------------------------------------

function toWorkflowDefinition(
  nodes: SkillNodeType[],
  edges: SkillEdgeType[],
  name?: string,
  version?: string,
): WorkflowDefinition {
  const nodeDefs: NodeDef[] = nodes.map((n) => ({
    id: n.id,
    skill: n.data.skill,
    ...(n.data.config && Object.keys(n.data.config).length > 0 ? { config: n.data.config } : {}),
  }));

  const edgeDefs: EdgeDef[] = edges.map((e) => ({
    from: e.source,
    to: e.target,
    type: (e.data?.edgeType as EdgeDef['type']) || 'serial',
  }));

  return { name, version, nodes: nodeDefs, edges: edgeDefs };
}

function fromWorkflowDefinition(
  def: WorkflowDefinition,
): { nodes: SkillNodeType[]; edges: SkillEdgeType[] } {
  // Auto-layout: arrange nodes in rows, 250px apart
  const COL_GAP = 250;
  const ROW_GAP = 120;
  const PER_ROW = 4;

  const nodeIds = new Set(def.nodes.map((n) => n.id));

  const nodes: SkillNodeType[] = def.nodes.map((nd, i) => {
    const col = i % PER_ROW;
    const row = Math.floor(i / PER_ROW);
    const category = CATEGORY_FOR_SKILL[nd.skill] || 'Data';
    return {
      id: nd.id,
      type: 'skillNode' as const,
      position: { x: 80 + col * COL_GAP, y: 80 + row * ROW_GAP },
      data: {
        skill: nd.skill,
        category,
        config: nd.config ?? {},
      },
    };
  });

  // Filter out edges that reference START/END (logical markers, not visual nodes)
  const visualEdges = def.edges.filter(
    (ed) => nodeIds.has(ed.from) && nodeIds.has(ed.to),
  );

  const edges: SkillEdgeType[] = visualEdges.map((ed, i) => ({
    id: `edge_${i}`,
    source: ed.from,
    target: ed.to,
    animated: ed.type === 'conditional',
    label: ed.type !== 'serial' ? ed.type : undefined,
    data: { edgeType: ed.type ?? 'serial' },
  }));

  // Reset counter so new nodes get unique ids
  const maxNum = def.nodes.reduce((max, n) => {
    const m = n.id.match(/^node_(\d+)$/);
    return m ? Math.max(max, parseInt(m[1], 10)) : max;
  }, 0);
  nodeIdCounter = maxNum;

  return { nodes, edges };
}

// ---------------------------------------------------------------------------
// WorkflowBuilderPage  -- main component
// ---------------------------------------------------------------------------

const WorkflowBuilderPage: React.FC = () => {
  const { id: workflowId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const reactFlowWrapper = useRef<HTMLDivElement>(null);

  // React Flow state
  const [nodes, setNodes, onNodesChange] = useNodesState<SkillNodeType>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<SkillEdgeType>([]);
  const [reactFlowInstance, setReactFlowInstance] = useState<any>(null);

  // UI state
  const [workflowName, setWorkflowName] = useState('Untitled Workflow');
  const [workflowDesc, setWorkflowDesc] = useState('');
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [templateModalOpen, setTemplateModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);

  // Derived selected objects
  const selectedNode = useMemo(
    () => (selectedNodeId ? (nodes.find((n) => n.id === selectedNodeId) as SkillNodeType | undefined) ?? null : null),
    [nodes, selectedNodeId],
  );
  const selectedEdge = useMemo(
    () => (selectedEdgeId ? edges.find((e) => e.id === selectedEdgeId) ?? null : null),
    [edges, selectedEdgeId],
  );

  // ---------- Load existing workflow ----------

  const { data: existingWorkflow } = useQuery({
    queryKey: ['workflow', workflowId],
    queryFn: () => workflowApi.get(workflowId!).then((r) => r.data),
    enabled: !!workflowId,
  });

  // When the existing workflow loads, populate canvas
  React.useEffect(() => {
    if (existingWorkflow) {
      setWorkflowName(existingWorkflow.name);
      setWorkflowDesc(existingWorkflow.description ?? '');
      const { nodes: n, edges: e } = fromWorkflowDefinition(existingWorkflow.definition);
      setNodes(n);
      setEdges(e);
    }
    // Only run when existingWorkflow changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existingWorkflow]);

  // When navigated from Gallery with a template in location.state, load it
  React.useEffect(() => {
    const state = location.state as { template?: WorkflowTemplate } | null;
    if (state?.template && !workflowId) {
      const tpl = state.template;
      const { nodes: n, edges: e } = fromWorkflowDefinition(tpl.definition);
      setNodes(n);
      setEdges(e);
      setWorkflowName(tpl.name);
      // Clear the state so it doesn't reload on re-render
      window.history.replaceState({}, '');
    }
    // Only run on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---------- Load templates ----------

  const { data: templates } = useQuery({
    queryKey: ['workflow-templates'],
    queryFn: () => workflowApi.templates().then((r) => r.data),
    enabled: templateModalOpen,
  });

  const loadTemplate = useCallback(
    (tpl: WorkflowTemplate) => {
      const { nodes: n, edges: e } = fromWorkflowDefinition(tpl.definition);
      setNodes(n);
      setEdges(e);
      setWorkflowName(tpl.name);
      setTemplateModalOpen(false);
      message.success(`Template "${tpl.name}" loaded`);
    },
    [setNodes, setEdges],
  );

  // ---------- Canvas interaction callbacks ----------

  const onConnect = useCallback(
    (connection: Connection) => {
      const newEdge: SkillEdgeType = {
        id: `edge_${Date.now()}`,
        source: connection.source!,
        target: connection.target!,
        sourceHandle: connection.sourceHandle ?? undefined,
        targetHandle: connection.targetHandle ?? undefined,
        data: { edgeType: 'serial' },
      };
      setEdges((eds) => [...eds, newEdge]);
    },
    [setEdges],
  );

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNodeId(node.id);
    setSelectedEdgeId(null);
  }, []);

  const onEdgeClick = useCallback((_: React.MouseEvent, edge: Edge) => {
    setSelectedEdgeId(edge.id);
    setSelectedNodeId(null);
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
  }, []);

  // ---------- Drag & drop from skill panel ----------

  const onDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();

      const skill = event.dataTransfer.getData('application/reactflow');
      if (!skill) return;

      const position = reactFlowInstance?.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      if (!position) return;

      const category = CATEGORY_FOR_SKILL[skill] || 'Data';
      const newNode: SkillNodeType = {
        id: nextNodeId(),
        type: 'skillNode' as const,
        position,
        data: { skill, category, config: {} },
      };

      setNodes((nds) => [...nds, newNode]);
    },
    [reactFlowInstance, setNodes],
  );

  // ---------- Node / edge updates from properties panel ----------

  const onUpdateNodeData = useCallback(
    (nodeId: string, patch: Partial<SkillNodeData>) => {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === nodeId ? { ...n, data: { ...n.data, ...patch } } : n,
        ),
      );
    },
    [setNodes],
  );

  const onUpdateEdgeType = useCallback(
    (edgeId: string, edgeType: EdgeDef['type']) => {
      setEdges((eds) =>
        eds.map((e): SkillEdgeType =>
          e.id === edgeId
            ? {
                ...e,
                animated: edgeType === 'conditional',
                label: edgeType !== 'serial' ? edgeType : undefined,
                data: { edgeType: edgeType ?? 'serial' },
              }
            : e,
        ),
      );
    },
    [setEdges],
  );

  const onDeleteNode = useCallback(
    (nodeId: string) => {
      setNodes((nds) => nds.filter((n) => n.id !== nodeId));
      setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
      setSelectedNodeId(null);
    },
    [setNodes, setEdges],
  );

  const onDeleteEdge = useCallback(
    (edgeId: string) => {
      setEdges((eds) => eds.filter((e) => e.id !== edgeId));
      setSelectedEdgeId(null);
    },
    [setEdges],
  );

  // ---------- Toolbar actions ----------

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      const definition = toWorkflowDefinition(nodes, edges, workflowName);
      if (workflowId) {
        await workflowApi.update(workflowId, {
          name: workflowName,
          description: workflowDesc,
          definition,
        });
        message.success('Workflow updated');
      } else {
        const { data } = await workflowApi.create({
          name: workflowName,
          description: workflowDesc,
          definition,
        });
        message.success('Workflow created');
        navigate(`/workflows/${data.id}/edit`, { replace: true });
      }
    } catch (err: any) {
      message.error(err.response?.data?.detail || 'Failed to save workflow');
    } finally {
      setSaving(false);
    }
  }, [nodes, edges, workflowName, workflowDesc, workflowId, navigate]);

  const handleValidate = useCallback(async () => {
    setValidating(true);
    try {
      const definition = toWorkflowDefinition(nodes, edges, workflowName);
      await workflowApi.validate({ name: workflowName, definition });
      message.success('Workflow is valid');
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      if (typeof detail === 'string') {
        message.error(detail);
      } else if (Array.isArray(detail)) {
        detail.forEach((d: any) => message.error(d.msg ?? JSON.stringify(d)));
      } else {
        message.error('Validation failed');
      }
    } finally {
      setValidating(false);
    }
  }, [nodes, edges, workflowName]);

  // ---------- Render ----------

  return (
    <Layout style={{ height: '100%', minHeight: 'calc(100vh - 64px)' }}>
      {/* --- Top toolbar --- */}
      <Header
        style={{
          background: '#fff',
          padding: '0 16px',
          borderBottom: '1px solid #f0f0f0',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          height: 52,
          lineHeight: '52px',
        }}
      >
        <Space>
          <Input
            value={workflowName}
            onChange={(e) => setWorkflowName(e.target.value)}
            style={{ width: 260, fontWeight: 600, fontSize: 15 }}
            variant="borderless"
          />
          <Input
            value={workflowDesc}
            onChange={(e) => setWorkflowDesc(e.target.value)}
            placeholder="Description (optional)"
            style={{ width: 260 }}
            variant="borderless"
          />
        </Space>

        <Space>
          <Tooltip title="Load from template">
            <Button icon={<FileOutlined />} onClick={() => setTemplateModalOpen(true)}>
              Load Template
            </Button>
          </Tooltip>
          <Tooltip title="Validate the workflow definition">
            <Button
              icon={<CheckCircleOutlined />}
              loading={validating}
              onClick={handleValidate}
            >
              Validate
            </Button>
          </Tooltip>
          <Tooltip title="Save workflow">
            <Button
              type="primary"
              icon={<SaveOutlined />}
              loading={saving}
              onClick={handleSave}
            >
              Save
            </Button>
          </Tooltip>
        </Space>
      </Header>

      <Layout>
        {/* --- Left sidebar: skill panel --- */}
        <Sider
          width={220}
          style={{
            background: '#fff',
            borderRight: '1px solid #f0f0f0',
            overflowY: 'auto',
          }}
        >
          <SkillPanel />
        </Sider>

        {/* --- Canvas --- */}
        <Content style={{ position: 'relative' }}>
          <div ref={reactFlowWrapper} style={{ width: '100%', height: '100%' }}>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onInit={setReactFlowInstance}
              onNodeClick={onNodeClick}
              onEdgeClick={onEdgeClick}
              onPaneClick={onPaneClick}
              onDrop={onDrop}
              onDragOver={onDragOver}
              nodeTypes={NODE_TYPES}
              fitView
              snapToGrid
              snapGrid={[16, 16]}
              deleteKeyCode={['Backspace', 'Delete']}
              style={{ background: '#f9fafb' }}
            >
              <Background gap={16} size={1} />
              <Controls />
              <MiniMap
                nodeStrokeWidth={3}
                zoomable
                pannable
                style={{ border: '1px solid #f0f0f0' }}
              />
            </ReactFlow>
          </div>
        </Content>

        {/* --- Right sidebar: properties panel --- */}
        <Sider
          width={260}
          style={{
            background: '#fff',
            borderLeft: '1px solid #f0f0f0',
            overflowY: 'auto',
          }}
        >
          <PropertiesPanel
            selectedNode={selectedNode}
            selectedEdge={selectedEdge}
            onUpdateNodeData={onUpdateNodeData}
            onUpdateEdgeType={onUpdateEdgeType}
            onDeleteNode={onDeleteNode}
            onDeleteEdge={onDeleteEdge}
          />
        </Sider>
      </Layout>

      {/* --- Template modal --- */}
      <Modal
        title="Load Workflow Template"
        open={templateModalOpen}
        onCancel={() => setTemplateModalOpen(false)}
        footer={null}
        width={520}
      >
        <List
          loading={!templates && templateModalOpen}
          dataSource={templates ?? []}
          locale={{ emptyText: 'No templates available' }}
          renderItem={(tpl: WorkflowTemplate) => (
            <List.Item
              actions={[
                <Button
                  key="load"
                  type="primary"
                  size="small"
                  onClick={() => loadTemplate(tpl)}
                >
                  Load
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={tpl.name}
                description={tpl.description}
              />
            </List.Item>
          )}
        />
      </Modal>
    </Layout>
  );
};

export default WorkflowBuilderPage;
