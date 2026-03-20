import OnboardingWizard from '../features/onboarding/OnboardingWizard';

export default function OnboardingPage() {
  return (
    <div className="min-h-screen bg-base-200 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl">
        <OnboardingWizard />
      </div>
    </div>
  );
}
