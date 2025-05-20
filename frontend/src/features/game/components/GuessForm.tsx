import React from 'react';
import { useGuess } from '../hooks/useGuess';

export default function GuessForm(): JSX.Element | null {
  const {
    code,
    disabled,
    error,
    remaining,
    visible,
    setCode,
    handleSubmit,
    dismiss,
  } = useGuess();

  if (!visible) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={dismiss}
      role="dialog"
      aria-modal="true"
    >
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        className="space-y-2 rounded bg-white p-4 shadow dark:bg-gray-800"
      >
        <label htmlFor="guess-code" className="block text-sm">
          Airport Code
        </label>
        <input
          id="guess-code"
          type="text"
          maxLength={4}
          className="w-full border p-2 text-black uppercase"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          disabled={disabled}
        />
        {remaining != null && (
          <p className="text-sm text-gray-600 dark:text-gray-300">
            Time left: {remaining}s
          </p>
        )}
        {error && <p className="text-sm text-red-500">{error}</p>}
        <button
          type="submit"
          disabled={disabled}
          className="w-full rounded bg-blue-500 px-3 py-1 text-white disabled:bg-gray-400"
        >
          Guess
        </button>
      </form>
    </div>
  );
}
