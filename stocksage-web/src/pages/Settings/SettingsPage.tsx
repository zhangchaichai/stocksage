import React, { useEffect } from 'react';
import { Button, Card, Form, Input, Select, Typography, message } from 'antd';
import { SaveOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { workflowApi } from '../../api/endpoints';
import { useI18n } from '../../i18n';

const STORAGE_KEY = 'stocksage_settings';

const LLM_PROVIDERS = [
  { label: 'DeepSeek', value: 'deepseek' },
  { label: 'OpenAI', value: 'openai' },
  { label: 'Anthropic', value: 'anthropic' },
  { label: 'Ollama', value: 'ollama' },
];

interface SettingsFormValues {
  llm_provider: string;
  api_key: string;
  default_workflow_id: string | undefined;
}

const loadSettings = (): Partial<SettingsFormValues> => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    // ignore parse errors
  }
  return {};
};

const saveSettings = (values: SettingsFormValues) => {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(values));
};

const SettingsPage: React.FC = () => {
  const [form] = Form.useForm<SettingsFormValues>();
  const { t } = useI18n();

  const { data: wfData } = useQuery({
    queryKey: ['workflows', 'list'],
    queryFn: () => workflowApi.list(0, 100).then((r) => r.data),
  });

  useEffect(() => {
    const saved = loadSettings();
    form.setFieldsValue(saved);
  }, [form]);

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      saveSettings(values);
      message.success(t.settings.saved);
    } catch {
      // validation errors handled by form
    }
  };

  return (
    <div>
      <Typography.Title level={4} style={{ marginBottom: 16 }}>{t.settings.title}</Typography.Title>

      <Card style={{ maxWidth: 600 }}>
        <Form form={form} layout="vertical">
          <Form.Item
            name="llm_provider"
            label={t.settings.llmProvider}
            rules={[{ required: true, message: 'Please select a provider' }]}
          >
            <Select placeholder={t.settings.selectProvider} options={LLM_PROVIDERS} />
          </Form.Item>

          <Form.Item
            name="api_key"
            label={t.settings.apiKey}
            rules={[{ required: true, message: 'Please enter your API key' }]}
          >
            <Input.Password placeholder={t.settings.enterApiKey} />
          </Form.Item>

          <Form.Item
            name="default_workflow_id"
            label={t.settings.defaultWorkflow}
          >
            <Select
              placeholder={t.settings.selectDefaultWorkflow}
              allowClear
              options={(wfData?.items || []).map((w) => ({
                label: w.name,
                value: w.id,
              }))}
            />
          </Form.Item>

          <Form.Item>
            <Button type="primary" icon={<SaveOutlined />} onClick={handleSave}>
              {t.common.save}
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
};

export default SettingsPage;
