import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getAuthStatus } from '../../api/auth';
import { useAuthStore } from '../../stores/authStore';
import { useUiStore } from '../../stores/uiStore';
import StepIndicator from '../../components/StepIndicator';
import WelcomeStep from './WelcomeStep';
import CredentialsStep from './CredentialsStep';
import LoginStep from './LoginStep';
import CompleteStep from './CompleteStep';

const multiUserSteps = ['Welcome', 'API Credentials', 'Login A', 'Login B', 'Complete'];
const singleUserSteps = ['Welcome', 'Login A', 'Login B', 'Complete'];

/** Detect single-user mode via GET /api/setup/mode. Falls back to multi-user (false) on error. */
async function detectSingleUserMode(): Promise<boolean> {
  try {
    const resp = await fetch('/api/setup/mode');
    if (!resp.ok) {
      console.error(`/api/setup/mode returned HTTP ${resp.status}`);
      return false;
    }
    const data = await resp.json();
    return data.single_user_mode === true;
  } catch (err) {
    console.error('Failed to detect setup mode:', err);
    return false;
  }
}

export default function OnboardingWizard() {
  const step = useUiStore((s) => s.onboardingStep);
  const setStep = useUiStore((s) => s.setOnboardingStep);
  const setAccount = useAuthStore((s) => s.setAccount);
  const navigate = useNavigate();
  const [singleUser, setSingleUser] = useState<boolean | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    async function init() {
      const isSingle = await detectSingleUserMode();
      setSingleUser(isSingle);

      // Check which accounts are already logged in
      try {
        const status = await getAuthStatus();
        const aLoggedIn = status.account_a?.is_authorized === true;
        const bLoggedIn = status.account_b?.is_authorized === true;

        if (aLoggedIn) setAccount('account_a', status.account_a!);
        if (bLoggedIn) setAccount('account_b', status.account_b!);

        if (aLoggedIn && bLoggedIn) {
          navigate('/dashboard', { replace: true });
          return;
        }

        // Auto-advance to the right step
        if (isSingle) {
          // single-user: 0=Welcome, 1=Login A, 2=Login B, 3=Complete
          if (aLoggedIn) setStep(2);       // skip to Login B
          else setStep(1);                  // skip Welcome, go to Login A
        } else {
          // multi-user: 0=Welcome, 1=Credentials, 2=Login A, 3=Login B, 4=Complete
          if (aLoggedIn) setStep(3);        // skip to Login B
          else if (status.has_credentials) setStep(2); // credentials set, go to Login A
          else setStep(0);                  // fresh user, start from Welcome
        }
      } catch (err) {
        console.error('Failed to check auth status during onboarding:', err);
        setStep(0);
      }

      setReady(true);
    }
    init();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (!ready || singleUser === null) {
    return <div className="flex justify-center p-8"><span className="loading loading-spinner loading-lg" /></div>;
  }

  const stepNames = singleUser ? singleUserSteps : multiUserSteps;

  if (singleUser) {
    return (
      <div className="card bg-base-100 shadow-xl">
        <div className="card-body">
          <StepIndicator steps={stepNames} current={step} />
          {step === 0 && <WelcomeStep onNext={() => setStep(1)} />}
          {step === 1 && <LoginStep account="account_a" onNext={() => setStep(2)} />}
          {step === 2 && <LoginStep account="account_b" onNext={() => setStep(3)} />}
          {step === 3 && <CompleteStep />}
        </div>
      </div>
    );
  }

  return (
    <div className="card bg-base-100 shadow-xl">
      <div className="card-body">
        <StepIndicator steps={stepNames} current={step} />
        {step === 0 && <WelcomeStep onNext={() => setStep(1)} />}
        {step === 1 && <CredentialsStep onNext={() => setStep(2)} />}
        {step === 2 && <LoginStep account="account_a" onNext={() => setStep(3)} />}
        {step === 3 && <LoginStep account="account_b" onNext={() => setStep(4)} />}
        {step === 4 && <CompleteStep />}
      </div>
    </div>
  );
}
