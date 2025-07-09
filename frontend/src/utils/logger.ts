/**
 * Frontend logging utility that captures console logs and sends them to the backend.
 * Preserves normal console behavior while also persisting logs to file.
 */

interface LogContext {
  [key: string]: string;
}

interface LogEntry {
  level: string;
  message: string;
  timestamp: number;
  context?: LogContext;
}

class Logger {
  private logQueue: LogEntry[] = [];
  private isProcessing = false;
  private batchSize = 10;
  private batchInterval = 5000; // 5 seconds
  private apiEndpoint = '/api/v0/logs/frontend';
  private originalConsole = {
    log: console.log,
    debug: console.debug,
    info: console.info,
    warn: console.warn,
    error: console.error,
  };

  constructor() {
    this.setupConsoleInterception();
    this.startBatchProcessor();
  }

  private setupConsoleInterception() {
    // Intercept console methods
    console.log = (...args: any[]) => {
      this.originalConsole.log(...args);
      this.log('info', this.formatMessage(args));
    };

    console.debug = (...args: any[]) => {
      this.originalConsole.debug(...args);
      this.log('debug', this.formatMessage(args));
    };

    console.info = (...args: any[]) => {
      this.originalConsole.info(...args);
      this.log('info', this.formatMessage(args));
    };

    console.warn = (...args: any[]) => {
      this.originalConsole.warn(...args);
      this.log('warn', this.formatMessage(args));
    };

    console.error = (...args: any[]) => {
      this.originalConsole.error(...args);
      this.log('error', this.formatMessage(args));
    };
  }

  private formatMessage(args: any[]): string {
    return args
      .map((arg) => {
        if (typeof arg === 'object') {
          try {
            return JSON.stringify(arg, null, 2);
          } catch {
            return String(arg);
          }
        }
        return String(arg);
      })
      .join(' ');
  }

  private log(level: string, message: string, context?: LogContext) {
    const entry: LogEntry = {
      level,
      message,
      timestamp: Date.now() / 1000, // Unix timestamp in seconds
      context,
    };

    this.logQueue.push(entry);

    // If queue is getting large, process immediately
    if (this.logQueue.length >= this.batchSize * 2) {
      this.processBatch();
    }
  }

  private startBatchProcessor() {
    setInterval(() => {
      if (this.logQueue.length > 0) {
        this.processBatch();
      }
    }, this.batchInterval);
  }

  private async processBatch() {
    if (this.isProcessing || this.logQueue.length === 0) {
      return;
    }

    this.isProcessing = true;
    const batch = this.logQueue.splice(0, this.batchSize);

    try {
      // Send logs one by one to match the API endpoint
      for (const entry of batch) {
        await fetch(this.apiEndpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(entry),
        });
      }
    } catch (error) {
      // Put logs back in queue if sending failed
      this.logQueue.unshift(...batch);
      // Use original console to avoid infinite loop
      this.originalConsole.error('Failed to send logs to server:', error);
    } finally {
      this.isProcessing = false;
    }
  }

  // Public methods for direct logging with context
  public debug(message: string, context?: LogContext) {
    console.debug(message);
    this.log('debug', message, context);
  }

  public info(message: string, context?: LogContext) {
    console.info(message);
    this.log('info', message, context);
  }

  public warn(message: string, context?: LogContext) {
    console.warn(message);
    this.log('warn', message, context);
  }

  public error(message: string, context?: LogContext) {
    console.error(message);
    this.log('error', message, context);
  }

  // Restore original console methods (useful for testing)
  public restore() {
    console.log = this.originalConsole.log;
    console.debug = this.originalConsole.debug;
    console.info = this.originalConsole.info;
    console.warn = this.originalConsole.warn;
    console.error = this.originalConsole.error;
  }
}

// Create singleton instance
const logger = new Logger();

// Export for direct usage
export default logger;

// Also export a function to initialize logging (can be called in main.tsx)
export function initializeLogging() {
  // Logger is already initialized via the singleton
  console.info('Frontend logging initialized');
}
