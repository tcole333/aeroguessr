import { Component, type ErrorInfo, type ReactNode } from 'react';

interface AppErrorBoundaryProps {
  children: ReactNode;
  renderFallback: (error: Error) => ReactNode;
}

interface AppErrorBoundaryState {
  error: Error | null;
}

function toError(value: unknown): Error {
  return value instanceof Error ? value : new Error(String(value));
}

function formatCrashReport(error: Error, componentStack: string | null | undefined): string {
  return [
    `[AppErrorBoundary] ${error.name}: ${error.message}`,
    error.stack ?? '',
    `Component stack:${componentStack ?? ''}`,
  ].join('\n');
}

/**
 * Catches render and lifecycle errors below it and shows a fallback instead of
 * unmounting the whole app. Errors thrown in event handlers or async callbacks
 * are not caught (React does not route those to error boundaries).
 */
export class AppErrorBoundary extends Component<AppErrorBoundaryProps, AppErrorBoundaryState> {
  state: AppErrorBoundaryState = { error: null };

  static getDerivedStateFromError(value: unknown): AppErrorBoundaryState {
    return { error: toError(value) };
  }

  componentDidCatch(value: unknown, info: ErrorInfo): void {
    console.error(formatCrashReport(toError(value), info.componentStack));
  }

  render(): ReactNode {
    const { error } = this.state;
    if (error) {
      return this.props.renderFallback(error);
    }
    return this.props.children;
  }
}
