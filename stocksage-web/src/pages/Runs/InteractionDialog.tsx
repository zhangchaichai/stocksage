import React, { useEffect, useState } from 'react';
import { Button, Input, Modal, Radio, Space, Typography } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { runApi } from '../../api/endpoints';

const { Text, Paragraph } = Typography;

interface InteractionDialogProps {
  runId: string;
  prompt: string;
  options: string[];
  timeout: number;
  onDismiss: () => void;
}

const InteractionDialog: React.FC<InteractionDialogProps> = ({
  runId,
  prompt,
  options,
  timeout,
  onDismiss,
}) => {
  const [selected, setSelected] = useState<string>(options[0] || '');
  const [customText, setCustomText] = useState('');
  const [useCustom, setUseCustom] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [remaining, setRemaining] = useState(timeout);

  // Countdown timer
  useEffect(() => {
    if (remaining <= 0) {
      onDismiss();
      return;
    }
    const timer = setInterval(() => {
      setRemaining((prev) => {
        if (prev <= 1) {
          onDismiss();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [remaining, onDismiss]);

  const handleSubmit = async () => {
    const response = useCustom ? customText : selected;
    if (!response.trim()) return;

    setSubmitting(true);
    try {
      await runApi.respond(runId, { response });
      onDismiss();
    } catch {
      // If interaction already expired, just dismiss
      onDismiss();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open
      title={
        <Space>
          <QuestionCircleOutlined style={{ color: '#1677ff' }} />
          <span>工作流需要您的输入</span>
        </Space>
      }
      onCancel={onDismiss}
      footer={[
        <Text key="timer" type="secondary" style={{ float: 'left', lineHeight: '32px' }}>
          {remaining}s 后自动继续
        </Text>,
        <Button key="skip" onClick={onDismiss}>
          跳过
        </Button>,
        <Button
          key="submit"
          type="primary"
          loading={submitting}
          onClick={handleSubmit}
          disabled={useCustom ? !customText.trim() : !selected}
        >
          确认
        </Button>,
      ]}
      closable={false}
      maskClosable={false}
    >
      <Paragraph style={{ marginBottom: 16 }}>{prompt}</Paragraph>

      {options.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <Radio.Group
            value={useCustom ? '__custom__' : selected}
            onChange={(e) => {
              if (e.target.value === '__custom__') {
                setUseCustom(true);
              } else {
                setUseCustom(false);
                setSelected(e.target.value);
              }
            }}
          >
            <Space direction="vertical">
              {options.map((opt) => (
                <Radio key={opt} value={opt}>
                  {opt}
                </Radio>
              ))}
              <Radio value="__custom__">自定义输入</Radio>
            </Space>
          </Radio.Group>
        </div>
      )}

      {(useCustom || options.length === 0) && (
        <Input.TextArea
          rows={3}
          value={customText}
          onChange={(e) => setCustomText(e.target.value)}
          placeholder="请输入您的回复..."
          autoFocus
        />
      )}
    </Modal>
  );
};

export default InteractionDialog;
