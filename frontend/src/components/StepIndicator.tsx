interface StepIndicatorProps {
  steps: string[];
  current: number;
}

export default function StepIndicator({ steps, current }: StepIndicatorProps) {
  return (
    <ul className="steps steps-horizontal w-full">
      {steps.map((label, i) => (
        <li
          key={label}
          className={`step ${i <= current ? 'step-primary' : ''}`}
        >
          <span className="hidden md:inline">{label}</span>
          <span className="md:hidden">{i + 1}</span>
        </li>
      ))}
    </ul>
  );
}
