import { Link } from 'react-router-dom';

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-base-200">
      {/* Hero Section */}
      <section className="hero min-h-[70vh]">
        <div className="hero-content text-center flex-col">
          <h1 className="text-5xl font-bold">Telegram Message Migrator</h1>
          <p className="py-6 text-lg max-w-2xl">
            Securely migrate messages between Telegram accounts with real-time
            progress tracking
          </p>
          <div className="flex flex-col sm:flex-row gap-4">
            <Link to="/onboarding" className="btn btn-primary btn-lg">
              Get Started
            </Link>
            <a href="#self-host" className="btn btn-ghost btn-lg">
              Self-Host
            </a>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="px-6 py-16 max-w-6xl mx-auto">
        <h2 className="text-3xl font-bold text-center mb-10">Features</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <div className="card bg-base-100 shadow-xl">
            <div className="card-body">
              <h3 className="card-title">
                <span className="text-2xl">🔀</span> Forward &amp; Copy
              </h3>
              <p>
                Forward messages instantly or copy with full media support up to
                4GB
              </p>
            </div>
          </div>
          <div className="card bg-base-100 shadow-xl">
            <div className="card-body">
              <h3 className="card-title">
                <span className="text-2xl">📊</span> Real-Time Progress
              </h3>
              <p>
                Watch your transfer progress live with SSE streaming updates
              </p>
            </div>
          </div>
          <div className="card bg-base-100 shadow-xl">
            <div className="card-body">
              <h3 className="card-title">
                <span className="text-2xl">🛡️</span> Smart Rate Limiting
              </h3>
              <p>
                7-layer rate limiter with jitter, batch cooldowns, and FloodWait
                auto-recovery
              </p>
            </div>
          </div>
          <div className="card bg-base-100 shadow-xl">
            <div className="card-body">
              <h3 className="card-title">
                <span className="text-2xl">📡</span> Live Forwarding
              </h3>
              <p>
                Monitor and auto-forward new messages as they arrive
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Security Section */}
      <section className="px-6 py-16 max-w-4xl mx-auto">
        <h2 className="text-3xl font-bold text-center mb-10">Security</h2>
        <div className="join join-vertical w-full">
          <div className="collapse collapse-arrow join-item bg-base-100 border border-base-300">
            <input type="radio" name="security-accordion" />
            <div className="collapse-title font-semibold">Open Source</div>
            <div className="collapse-content">
              <p>
                MIT License. Full source code auditable on GitHub. No hidden
                data collection, no telemetry.
              </p>
            </div>
          </div>
          <div className="collapse collapse-arrow join-item bg-base-100 border border-base-300">
            <input type="radio" name="security-accordion" />
            <div className="collapse-title font-semibold">
              Encrypted Storage
            </div>
            <div className="collapse-content">
              <p>
                AES-256-GCM encryption for stored credentials with HKDF key
                derivation per user. Your API keys are never stored in
                plaintext.
              </p>
            </div>
          </div>
          <div className="collapse collapse-arrow join-item bg-base-100 border border-base-300">
            <input type="radio" name="security-accordion" />
            <div className="collapse-title font-semibold">Minimal Data</div>
            <div className="collapse-content">
              <p>
                No message content stored. Transfer state lives in RAM only.
                Only encrypted credentials persist in the database.
              </p>
            </div>
          </div>
          <div className="collapse collapse-arrow join-item bg-base-100 border border-base-300">
            <input type="radio" name="security-accordion" />
            <div className="collapse-title font-semibold">Self-Hosting</div>
            <div className="collapse-content">
              <p>
                Run your own instance for complete control over your data. No
                third-party servers involved.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Self-Host Guide Section */}
      <section id="self-host" className="px-6 py-16 max-w-4xl mx-auto">
        <h2 className="text-3xl font-bold text-center mb-10">
          Self-Host in 3 Steps
        </h2>
        <div className="mockup-code bg-base-100 shadow-xl">
          <pre data-prefix="1">
            <code>git clone https://github.com/user/telegram-message-migrator</code>
          </pre>
          <pre data-prefix="2">
            <code>cp .env.example .env  # Edit: set SERVER_SECRET</code>
          </pre>
          <pre data-prefix="3">
            <code>docker compose up -d</code>
          </pre>
        </div>
        <div className="mt-8 space-y-3 text-sm">
          <p>
            <strong>Step 1:</strong> Clone the repository to your server.
          </p>
          <p>
            <strong>Step 2:</strong> Copy the example environment file and set
            your <code className="badge badge-neutral badge-sm">SERVER_SECRET</code> for
            credential encryption.
          </p>
          <p>
            <strong>Step 3:</strong> Start the application with Docker Compose.
            The app will be available on port 8000.
          </p>
        </div>
      </section>

      {/* FAQ Section */}
      <section className="px-6 py-16 max-w-4xl mx-auto">
        <h2 className="text-3xl font-bold text-center mb-10">FAQ</h2>
        <div className="join join-vertical w-full">
          <div className="collapse collapse-arrow join-item bg-base-100 border border-base-300">
            <input type="radio" name="faq-accordion" />
            <div className="collapse-title font-semibold">
              Is my Telegram account safe?
            </div>
            <div className="collapse-content">
              <p>
                Yes. The migrator uses conservative rate limiting with 7 layers
                of protection including jitter, batch cooldowns, daily caps, and
                automatic FloodWait respect. If Telegram signals to slow down,
                the tool obeys immediately and reduces its speed.
              </p>
            </div>
          </div>
          <div className="collapse collapse-arrow join-item bg-base-100 border border-base-300">
            <input type="radio" name="faq-accordion" />
            <div className="collapse-title font-semibold">
              What data is stored?
            </div>
            <div className="collapse-content">
              <p>
                Only encrypted API credentials and session metadata. No messages
                are ever stored. Transfer history and progress live in memory
                only and are lost on restart.
              </p>
            </div>
          </div>
          <div className="collapse collapse-arrow join-item bg-base-100 border border-base-300">
            <input type="radio" name="faq-accordion" />
            <div className="collapse-title font-semibold">
              Can I self-host?
            </div>
            <div className="collapse-content">
              <p>
                Yes. Deploy with a single Docker Compose command. In self-hosted
                mode, you have complete control over your data and
                don&apos;t even need a server secret if running locally.
              </p>
            </div>
          </div>
          <div className="collapse collapse-arrow join-item bg-base-100 border border-base-300">
            <input type="radio" name="faq-accordion" />
            <div className="collapse-title font-semibold">
              What are API credentials?
            </div>
            <div className="collapse-content">
              <p>
                Telegram API credentials (<code className="badge badge-neutral badge-sm">api_id</code> and{' '}
                <code className="badge badge-neutral badge-sm">api_hash</code>) are keys that let
                the app communicate with Telegram on your behalf. You&apos;ll be
                guided through getting them during onboarding.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="footer footer-center bg-base-100 p-10">
        <div>
          <p>
            <a
              href="https://github.com/user/telegram-message-migrator"
              className="link link-hover"
              target="_blank"
              rel="noopener noreferrer"
            >
              Open Source on GitHub
            </a>
          </p>
          <p className="text-base-content/60">Built with FastAPI + React</p>
        </div>
      </footer>
    </div>
  );
}
