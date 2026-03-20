interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export default function LoadingSpinner({
  size = 'lg',
  className = '',
}: LoadingSpinnerProps) {
  const sizeClass =
    size === 'sm'
      ? 'loading-sm'
      : size === 'md'
        ? 'loading-md'
        : 'loading-lg';

  return (
    <div className={`flex items-center justify-center ${className}`}>
      <span className={`loading loading-spinner ${sizeClass}`} />
    </div>
  );
}
