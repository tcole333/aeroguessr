import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HostIndicator } from './HostIndicator';

describe('HostIndicator', () => {
  describe('badge variant', () => {
    it('renders badge when isHost is true', () => {
      render(<HostIndicator isHost={true} variant="badge" />);

      const badge = screen.getByRole('status', { name: 'Host player' });
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent('Host');
      expect(badge).toHaveClass('bg-blue-100');
    });

    it('does not render when isHost is false', () => {
      render(<HostIndicator isHost={false} variant="badge" />);

      expect(screen.queryByRole('status')).not.toBeInTheDocument();
    });

    it('applies custom className', () => {
      render(<HostIndicator isHost={true} variant="badge" className="ml-2" />);

      const badge = screen.getByRole('status');
      expect(badge).toHaveClass('ml-2');
    });
  });

  describe('inline variant', () => {
    it('renders inline icon when isHost is true', () => {
      render(<HostIndicator isHost={true} variant="inline" />);

      const indicator = screen.getByRole('status', { name: 'Host player' });
      expect(indicator).toBeInTheDocument();
      expect(indicator).toHaveTextContent('Host');
      expect(indicator).toHaveAttribute('title', 'Host');
    });

    it('does not render when isHost is false', () => {
      render(<HostIndicator isHost={false} variant="inline" />);

      expect(screen.queryByRole('status')).not.toBeInTheDocument();
    });

    it('applies custom className', () => {
      render(<HostIndicator isHost={true} variant="inline" className="text-lg" />);

      const indicator = screen.getByRole('status');
      expect(indicator).toHaveClass('text-lg');
    });
  });

  describe('default variant', () => {
    it('defaults to badge variant when not specified', () => {
      render(<HostIndicator isHost={true} />);

      const badge = screen.getByRole('status');
      expect(badge).toHaveTextContent('Host');
    });
  });

  describe('accessibility', () => {
    it('has proper ARIA attributes for badge variant', () => {
      render(<HostIndicator isHost={true} variant="badge" />);

      const badge = screen.getByRole('status', { name: 'Host player' });
      expect(badge).toBeInTheDocument();
    });

    it('has proper ARIA attributes for inline variant', () => {
      render(<HostIndicator isHost={true} variant="inline" />);

      const indicator = screen.getByRole('status', { name: 'Host player' });
      expect(indicator).toHaveAttribute('title', 'Host');
    });
  });
});
