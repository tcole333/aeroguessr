interface MapPlaceholderProps {
  /** Whether loading the client config failed, rather than still being under way. */
  failed: boolean;
  onRetry: () => void;
}

/** Fills the map's space until the client config says where the map is. */
export default function MapPlaceholder({ failed, onRetry }: MapPlaceholderProps): JSX.Element {
  if (!failed) {
    return (
      <div
        role="status"
        className="flex h-full w-full items-center justify-center text-sm text-gray-500 dark:text-gray-400"
      >
        Loading map…
      </div>
    );
  }

  return (
    <div
      role="alert"
      className="flex h-full w-full flex-col items-center justify-center gap-3 p-4 text-center text-sm text-gray-600 dark:text-gray-300"
    >
      <p>Couldn&apos;t load the map.</p>
      <button
        type="button"
        onClick={onRetry}
        className="rounded border border-gray-400 px-3 py-1 font-semibold hover:bg-gray-200 dark:hover:bg-gray-700"
      >
        Try again
      </button>
    </div>
  );
}
