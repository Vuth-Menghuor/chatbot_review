/**
 * Chat API models management composable.
 */

import type {
  ChatApiDownloadRequest,
  ChatApiDownloadResponse,
  ChatApiDownloadStatus,
  ChatApiHttpConfig,
  ChatApiLoadModelRequest,
  ChatApiLoadModelResponse,
  ChatApiModel,
  ChatApiModelsListResponse,
  UseChatApiModelsConfig,
} from '~/types/message';
import { chatApiFetchJson } from './chatApiHttp';

export function useChatApiModels(config: UseChatApiModelsConfig) {
  if (!config.baseUrl) throw new Error('Chat API base URL is not configured');
  const http: ChatApiHttpConfig = { baseUrl: config.baseUrl, apiToken: config.apiToken };

  /** `GET /api/v1/models` — native list. */
  async function list(signal?: AbortSignal): Promise<ChatApiModel[]> {
    const raw = await chatApiFetchJson<ChatApiModelsListResponse>(http, {
      path: '/api/v1/models',
      method: 'GET',
      signal,
    });
    return raw.data ?? raw.models ?? [];
  }

  /** `GET /v1/models` — OpenAI-compatible list. */
  async function listOpenAi(signal?: AbortSignal): Promise<ChatApiModel[]> {
    const raw = await chatApiFetchJson<ChatApiModelsListResponse>(http, {
      path: '/v1/models',
      method: 'GET',
      signal,
    });
    return raw.data ?? raw.models ?? [];
  }

  /** `POST /api/v1/models/load` — load a model. */
  async function load(
    body: ChatApiLoadModelRequest,
    signal?: AbortSignal,
  ): Promise<ChatApiLoadModelResponse> {
    return chatApiFetchJson<ChatApiLoadModelResponse>(http, {
      path: '/api/v1/models/load',
      body,
      signal,
    });
  }

  /** `POST /api/v1/models/download` — start a download. */
  async function download(
    body: ChatApiDownloadRequest,
    signal?: AbortSignal,
  ): Promise<ChatApiDownloadResponse> {
    return chatApiFetchJson<ChatApiDownloadResponse>(http, {
      path: '/api/v1/models/download',
      body,
      signal,
    });
  }

  /**
   * `GET /api/v1/models/download/status:{job_id}` — poll a download job.
   */
  async function downloadStatus(
    jobId: string,
    signal?: AbortSignal,
  ): Promise<ChatApiDownloadStatus> {
    if (!jobId) throw new Error('downloadStatus requires a jobId');
    const safeId = encodeURIComponent(jobId);
    return chatApiFetchJson<ChatApiDownloadStatus>(http, {
      path: `/api/v1/models/download/status:${safeId}`,
      method: 'GET',
      signal,
    });
  }

  /**
   * Convenience: poll `downloadStatus` until terminal.
   */
  async function awaitDownload(
    jobId: string,
    options: {
      intervalMs?: number;
      timeoutMs?: number;
      signal?: AbortSignal;
      onProgress?: (status: ChatApiDownloadStatus) => void;
    } = {},
  ): Promise<ChatApiDownloadStatus> {
    const interval = options.intervalMs ?? 1500;
    const deadline = options.timeoutMs ? Date.now() + options.timeoutMs : Infinity;

    const isTerminal = (s: string) =>
      s === 'completed' || s === 'error' || s === 'cancelled' || s === 'failed';

    while (true) {
      if (options.signal?.aborted) throw new Error('aborted');
      if (Date.now() > deadline) throw new Error('downloadStatus timed out');

      const status = await downloadStatus(jobId, options.signal);
      options.onProgress?.(status);
      if (isTerminal(String(status.status))) return status;

      await new Promise<void>((resolve) => setTimeout(resolve, interval));
    }
  }

  return {
    list,
    listOpenAi,
    load,
    download,
    downloadStatus,
    awaitDownload,
  };
}
