import test from 'node:test';
import assert from 'node:assert/strict';

import {
  isCalculatorReportDraftText,
  isUnreliableServiceFallbackText,
} from '../../app/utils/chat/chatText';

test('calculator report drafts are treated as unreliable calculator fallback text', () => {
  const draft = 'IMPORT TAX CALCULATION\n\nPRODUCT INFORMATION\n\nINPUT PARAMETERS';

  assert.equal(isCalculatorReportDraftText(draft), true);
  assert.equal(isUnreliableServiceFallbackText(draft, { service: 'calculator', intent: 'calculation' }), true);
});

test('general context does not suppress normal general answers', () => {
  assert.equal(
    isUnreliableServiceFallbackText('Hello! How can I help you?', { service: 'general', intent: 'general' }),
    false,
  );
});
