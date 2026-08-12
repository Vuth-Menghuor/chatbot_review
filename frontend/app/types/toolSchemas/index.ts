import type { InteractionToolData } from '../unified';

function asRecord(data: unknown): Record<string, unknown> {
  return data && typeof data === 'object' && !Array.isArray(data)
    ? (data as Record<string, unknown>)
    : {};
}

export function normalizeToolData(type: string, data: unknown): unknown {
  const normalizedType = String(type || '').toLowerCase();

  if (normalizedType === 'code') {
    if (typeof data === 'string') return data;
    const record = asRecord(data);
    return String(record.code ?? record.content ?? JSON.stringify(data, null, 2));
  }

  if (normalizedType === 'table') {
    const record = asRecord(data);
    return {
      columns: Array.isArray(record.columns) ? record.columns : undefined,
      rows: Array.isArray(record.rows) ? record.rows : Array.isArray(data) ? data : [],
      title: typeof record.title === 'string' ? record.title : undefined,
    };
  }

  if (normalizedType === 'workflow') {
    const record = asRecord(data);
    return {
      title: typeof record.title === 'string' ? record.title : record.intent,
      intent: record.intent,
      workflowSteps: Array.isArray(record.workflowSteps) ? record.workflowSteps : [],
    };
  }

  if (normalizedType === 'ocr') {
    const record = asRecord(data);
    return {
      text: typeof record.text === 'string' ? record.text : '',
      title: typeof record.title === 'string' ? record.title : undefined,
      language: record.language,
      confidence: record.confidence,
      pages: record.pages,
      fields: record.fields,
    };
  }

  if (normalizedType === 'prediction') {
    const record = asRecord(data);
    return {
      title: typeof record.title === 'string' ? record.title : undefined,
      label: typeof record.label === 'string' ? record.label : undefined,
      hsCode: typeof record.hsCode === 'string' ? record.hsCode : undefined,
      productName: typeof record.productName === 'string' ? record.productName : undefined,
      category: typeof record.category === 'string' ? record.category : undefined,
      predictedVolume:
        record.predictedVolume != null ? Number(record.predictedVolume) : undefined,
      year: record.year != null ? Number(record.year) : undefined,
      value: record.value,
      unit: typeof record.unit === 'string' ? record.unit : undefined,
      metrics: Array.isArray(record.metrics) ? record.metrics : undefined,
      reason: typeof record.reason === 'string' ? record.reason : undefined,
      evidence: Array.isArray(record.evidence) ? record.evidence : undefined,
      sourceName: typeof record.sourceName === 'string' ? record.sourceName : undefined,
      sourceUrl: typeof record.sourceUrl === 'string' ? record.sourceUrl : undefined,
      tariffSectionTitle:
        typeof record.tariffSectionTitle === 'string' ? record.tariffSectionTitle : undefined,
      taxRates: Array.isArray(record.taxRates) ? record.taxRates : undefined,
      importDuty: typeof record.importDuty === 'string' ? record.importDuty : undefined,
      specialTax: typeof record.specialTax === 'string' ? record.specialTax : undefined,
      vat: typeof record.vat === 'string' ? record.vat : undefined,
      exportTax: typeof record.exportTax === 'string' ? record.exportTax : undefined,
      alternatives: Array.isArray(record.alternatives) ? record.alternatives : undefined,
    };
  }

  if (normalizedType === 'chart' || normalizedType === 'report' || normalizedType === 'image') {
    return asRecord(data);
  }

  if (normalizedType === 'interaction') {
    const record = asRecord(data);
    const interaction = (record.interaction && typeof record.interaction === 'object'
      ? record.interaction
      : record) as InteractionToolData;
    return {
      kind: interaction.kind ?? 'form',
      title: interaction.title,
      description: interaction.description,
      requestId: interaction.requestId,
      toolName: interaction.toolName,
      fields: Array.isArray(interaction.fields) ? interaction.fields : [],
      actions: Array.isArray(interaction.actions) ? interaction.actions : [],
    };
  }

  return data;
}
