import React, { useEffect, useRef, useState } from 'react';
import {
  Badge,
  Button,
  Drawer,
  Input,
  Space,
  Spin,
  Typography,
} from 'antd';
import {
  MessageOutlined,
  SendOutlined,
  LinkOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useChatStore } from '../../stores/chatStore';
import { useI18n } from '../../i18n';

const ChatDrawer: React.FC = () => {
  const { t } = useI18n();
  const navigate = useNavigate();
  const { open, messages, loading, toggleOpen, sendMessage, loadHistory } = useChatStore();
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [historyLoaded, setHistoryLoaded] = useState(false);

  useEffect(() => {
    if (open && !historyLoaded) {
      loadHistory();
      setHistoryLoaded(true);
    }
  }, [open, historyLoaded, loadHistory]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput('');

    const result = await sendMessage(text);
    if (result?.action === 'navigate' && result.data?.route) {
      navigate(result.data.route as string);
    } else if (result?.action === 'run_analysis' && result.data?.route) {
      // Don't auto-navigate, show link in chat
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <>
      {/* FAB */}
      <Button
        type="primary"
        shape="circle"
        size="large"
        icon={<MessageOutlined />}
        onClick={toggleOpen}
        style={{
          position: 'fixed',
          bottom: 24,
          right: 24,
          width: 56,
          height: 56,
          fontSize: 24,
          zIndex: 1000,
          boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
        }}
      />

      <Drawer
        title={t.chat.title}
        placement="bottom"
        height="60%"
        open={open}
        onClose={toggleOpen}
        styles={{ body: { padding: 0, display: 'flex', flexDirection: 'column' } }}
      >
        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
          {messages.length === 0 && (
            <Typography.Paragraph type="secondary" style={{ textAlign: 'center', paddingTop: 40 }}>
              {t.chat.welcomeHint}
            </Typography.Paragraph>
          )}

          {messages.map((msg) => (
            <div
              key={msg.id}
              style={{
                display: 'flex',
                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                marginBottom: 8,
              }}
            >
              <div
                style={{
                  maxWidth: '75%',
                  padding: '8px 12px',
                  borderRadius: 8,
                  background: msg.role === 'user' ? '#1677ff' : '#f0f0f0',
                  color: msg.role === 'user' ? '#fff' : '#000',
                }}
              >
                <div style={{ whiteSpace: 'pre-wrap' }}>{String(msg.content)}</div>
                {msg.action === 'run_analysis' && !!msg.data?.route && (
                  <Button
                    type="link"
                    icon={<LinkOutlined />}
                    size="small"
                    style={{ padding: 0, color: msg.role === 'user' ? '#fff' : undefined }}
                    onClick={() => {
                      navigate(msg.data!.route as string);
                      toggleOpen();
                    }}
                  >
                    {t.chat.viewAnalysis}
                  </Button>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div style={{ textAlign: 'center', padding: 8 }}>
              <Spin size="small" />
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div style={{ padding: '8px 16px', borderTop: '1px solid #f0f0f0' }}>
          <Space.Compact style={{ width: '100%' }}>
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t.chat.inputPlaceholder}
              disabled={loading}
              size="large"
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={handleSend}
              loading={loading}
              size="large"
            />
          </Space.Compact>
        </div>
      </Drawer>
    </>
  );
};

export default ChatDrawer;
