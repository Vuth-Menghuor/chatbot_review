import type {
  ChatApiCallResult,
  ChatApiClientConfig,
  ChatApiRequest,
  ChatApiResponse,
  ChatApiSendOptions,
} from '~/types/message';
import { chatApiResponseToUnified } from './chatApiAdapter';
import { chatApiFetchJson } from './chatApiHttp';

const DEFAULT_CONTEXT_LENGTH = 8000;
const DEFAULT_TEMPERATURE = 0;

export { ChatApiRequestError } from './chatApiHttp';

export function isChatApiConfigured(config: Partial<ChatApiClientConfig>): boolean {
  const transport = (config as Partial<ChatApiClientConfig> & { transport?: string }).transport;
  return Boolean(config.baseUrl && (transport === 'gdce' || config.model));
}

/**
 * Lightweight client around Chat API's native `/api/v1/chat` endpoint.
 */
export function useChatApiClient(config: ChatApiClientConfig) {
  if (!config.baseUrl) throw new Error('Chat API base URL is not configured');
  if (!config.model) throw new Error('Chat API model is not configured');

  async function send(options: ChatApiSendOptions): Promise<ChatApiCallResult> {
    const body: ChatApiRequest = {
      model: config.model,
      input: options.input,
      ...(options.integrations?.length ? { integrations: options.integrations } : {}),
      context_length:
        options.contextLength ?? config.contextLength ?? DEFAULT_CONTEXT_LENGTH,
      temperature:
        options.temperature ?? config.temperature ?? DEFAULT_TEMPERATURE,
    };

    const raw = await chatApiFetchJson<ChatApiResponse>(
      { baseUrl: config.baseUrl, apiToken: config.apiToken },
      { path: '/api/v1/chat', body, signal: options.signal },
    );

    return { unified: chatApiResponseToUnified(raw), raw };
  }

  return { send, endpoint: `${config.baseUrl}/api/v1/chat` };
}
