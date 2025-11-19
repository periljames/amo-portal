import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import AuthLayout from "../components/Layout/AuthLayout";
import TextField from "../components/UI/TextField";
import Button from "../components/UI/Button";
import { login } from "../services/auth";

const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);

    if (!email || !password) {
      setErrorMsg("Please enter both email and password.");
      return;
    }

    try {
      setLoading(true);
      await login(email, password);
      navigate("/", { replace: true });
    } catch (err: any) {
      console.error(err);
      setErrorMsg("Invalid email or password.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout
      title="Sign in to AMO Portal"
      subtitle="Use your Safarilink AMO credentials."
    >
      <form className="auth-form" onSubmit={handleSubmit}>
        {errorMsg && <div className="auth-form__error">{errorMsg}</div>}

        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          name="email"
          required
        />

        <TextField
          label="Password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          name="password"
          required
        />

        <div className="auth-form__actions">
          <Button type="submit" loading={loading}>
            Sign in
          </Button>
        </div>
      </form>
    </AuthLayout>
  );
};

export default LoginPage;
