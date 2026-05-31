// Optional: configure or set up a testing framework before each test.
// If you delete this file, remove `setupFilesAfterEnv` from `jest.config.js`

// Learn more: https://jestjs.io/docs/configuration#setupfilesafterenv-array

// Mock environment variables for testing
process.env.NODE_ENV = 'test'

// Increase timeout for integration tests
jest.setTimeout(30000)

// Mock console methods to reduce noise in tests
global.console = {
  ...console,
  // Uncomment to ignore specific log levels in tests
  // log: jest.fn(),
  // debug: jest.fn(),
  // info: jest.fn(),
  // warn: jest.fn(),
  // error: jest.fn(),
}