export class DataFileMissingError extends Error {
  readonly code = "DATA_FILE_MISSING";

  constructor(
    message: string,
    readonly localPath: string,
    readonly gcsPath: string,
  ) {
    super(message);
    this.name = "DataFileMissingError";
  }
}

export class DataFileLoadError extends Error {
  readonly code = "DATA_FILE_LOAD_ERROR";

  constructor(
    message: string,
    readonly localPath: string,
    readonly gcsPath: string,
    readonly causeMessage: string,
  ) {
    super(message);
    this.name = "DataFileLoadError";
  }
}
