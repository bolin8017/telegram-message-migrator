interface WelcomeStepProps {
  onNext: () => void;
}

export default function WelcomeStep({ onNext }: WelcomeStepProps) {
  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold">Welcome to Telegram Message Migrator</h2>
        <p className="mt-2 text-base-content/70">
          Migrate messages between two Telegram accounts safely and efficiently.
        </p>
      </div>

      <div className="divider" />

      <div>
        <h3 className="text-lg font-semibold mb-3">What you'll need</h3>
        <ul className="space-y-2">
          <li className="flex items-start gap-2">
            <span className="badge badge-primary badge-sm mt-1">1</span>
            <span>
              <strong>Two Telegram accounts</strong> — a source account and a
              destination account
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="badge badge-primary badge-sm mt-1">2</span>
            <span>
              <strong>API credentials</strong> from{' '}
              <a
                href="https://my.telegram.org"
                target="_blank"
                rel="noopener noreferrer"
                className="link link-primary"
              >
                my.telegram.org
              </a>
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span className="badge badge-primary badge-sm mt-1">3</span>
            <span>
              <strong>Verification codes</strong> — sent to your Telegram app
              when you log in
            </span>
          </li>
        </ul>
      </div>

      <div className="card-actions justify-end pt-4">
        <button className="btn btn-primary" onClick={onNext}>
          Let's Get Started
        </button>
      </div>
    </div>
  );
}
