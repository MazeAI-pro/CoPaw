import { useMemo, useState } from "react";
import { Alert, Button, Card, Form, Input, Tabs, Typography } from "antd";
import { Navigate } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";

export default function LoginPage() {
  const { user, loading, supabaseEnabled, loginWithCredentials, loginWithSupabase } = useAuth();
  const [legacySubmitting, setLegacySubmitting] = useState(false);
  const [supabaseSubmitting, setSupabaseSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tabItems = useMemo(() => {
    const items = [
      {
        key: "legacy",
        label: "Admin Login",
        children: (
          <Form
            layout="vertical"
            onFinish={async (values: { username: string; password: string }) => {
              setError(null);
              setLegacySubmitting(true);
              try {
                await loginWithCredentials(values.username, values.password);
              } catch (err) {
                setError((err as Error).message || "Login failed");
              } finally {
                setLegacySubmitting(false);
              }
            }}
          >
            <Form.Item name="username" label="Username" rules={[{ required: true }]}>
              <Input autoComplete="username" />
            </Form.Item>
            <Form.Item name="password" label="Password" rules={[{ required: true }]}>
              <Input.Password autoComplete="current-password" />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={legacySubmitting} block>
              Login
            </Button>
          </Form>
        ),
      },
    ];

    if (supabaseEnabled) {
      items.push({
        key: "supabase",
        label: "Email Login",
        children: (
          <Form
            layout="vertical"
            onFinish={async (values: { email: string; password: string }) => {
              setError(null);
              setSupabaseSubmitting(true);
              try {
                await loginWithSupabase(values.email, values.password);
              } catch (err) {
                setError((err as Error).message || "Login failed");
              } finally {
                setSupabaseSubmitting(false);
              }
            }}
          >
            <Form.Item name="email" label="Email" rules={[{ required: true, type: "email" }]}>
              <Input autoComplete="email" />
            </Form.Item>
            <Form.Item name="password" label="Password" rules={[{ required: true }]}>
              <Input.Password autoComplete="current-password" />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={supabaseSubmitting} block>
              Login with Supabase
            </Button>
          </Form>
        ),
      });
    }
    return items;
  }, [legacySubmitting, loginWithCredentials, loginWithSupabase, supabaseEnabled, supabaseSubmitting]);

  if (loading) {
    return null;
  }
  if (user) {
    return <Navigate to="/" replace />;
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
        padding: 16,
      }}
    >
      <Card style={{ width: 420 }}>
        <Typography.Title level={3} style={{ textAlign: "center", marginBottom: 24 }}>
          CoPaw
        </Typography.Title>
        {error ? <Alert type="error" message={error} style={{ marginBottom: 16 }} /> : null}
        <Tabs defaultActiveKey="legacy" items={tabItems} />
      </Card>
    </div>
  );
}
