import { classNames } from '../lib/utils';

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className={classNames('brand', compact && 'brand-compact')} aria-label="JARVIS">
      <svg className="brand-mark" viewBox="0 0 44 48" fill="none" aria-hidden="true">
        <path d="M22 2.5 41 13.25v21.5L22 45.5 3 34.75v-21.5L22 2.5Z" stroke="currentColor" strokeWidth="1.5" />
        <path d="M22 8.5 36 16.25v15.5L22 39.5 8 31.75v-15.5L22 8.5Z" stroke="currentColor" strokeOpacity=".32" />
        <path d="m25.5 12-11 16h7l-2.5 9 11-17h-7l2.5-8Z" fill="currentColor" />
      </svg>
      {!compact && (
        <div className="brand-copy">
          <strong>JARVIS</strong>
          <span>Personal intelligence</span>
        </div>
      )}
    </div>
  );
}
