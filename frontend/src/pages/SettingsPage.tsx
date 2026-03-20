import SettingsPanel from '../features/settings/SettingsPanel';

export default function SettingsPage() {
  return (
    <div className="max-w-2xl mx-auto p-4">
      <h1 className="text-2xl font-bold mb-6">Settings</h1>
      <SettingsPanel />
    </div>
  );
}
