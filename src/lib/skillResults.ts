import { formatLegalChatResult } from './legal';

function list(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null) : [];
}

function record(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function bytes(value: unknown): string {
  const total = Number(value ?? 0);
  if (total >= 1_000_000) return `${(total / 1_000_000).toFixed(2)} MB`;
  if (total >= 1_000) return `${(total / 1_000).toFixed(1)} KB`;
  return `${total} B`;
}

function formatReverseChatResult(skillId: string, result: Record<string, unknown>): string {
  if (skillId === 'reverse.inspect') {
    const identity = record(result.identity);
    const counts = record(result.counts);
    const entropy = record(result.entropy);
    const attention = list(result.topFindings).filter((finding) => String(finding.severity) === 'attention');
    return [
      `${String(identity.path)} · ${String(result.format)} · ${bytes(identity.bytes)}`,
      `SHA-256: ${String(identity.sha256)}`,
      `Entropia ${Number(entropy.fileEntropy ?? 0).toFixed(3)} · ${Number(counts.sections ?? 0)} seções · ${Number(counts.segments ?? 0)} segmentos · ${Number(counts.entries ?? 0)} entradas · ${Number(counts.imports ?? 0)} imports.`,
      attention.length ? `Atenção:\n${attention.slice(0, 4).map((finding) => `• ${String(finding.message)}`).join('\n')}` : '',
      'Nada foi executado. Abra Reversa para ver fatos, evidências e limites declarados.',
    ].filter(Boolean).join('\n\n');
  }
  if (skillId === 'reverse.layout') {
    const sections = list(result.sections);
    const imports = list(result.imports);
    const findings = list(result.findings);
    return [
      `${String(record(result.identity).path)} · ${String(result.format)}`,
      `${sections.length} seções e ${list(result.segments).length} segmentos inventariados.`,
      sections.length ? `Seções: ${sections.slice(0, 8).map((section) => String(section.name || '(sem nome)')).join(', ')}${sections.length > 8 ? '…' : ''}.` : '',
      imports.length ? `Bibliotecas: ${imports.slice(0, 6).map((item) => String(item.library)).join(', ')}${imports.length > 6 ? '…' : ''}.` : 'Nenhuma biblioteca importada identificada.',
      findings.length ? `Achados: ${findings.slice(0, 4).map((item) => String(item.message)).join(' ')}` : '',
      'Análise estática; o artefato não foi carregado nem executado.',
    ].filter(Boolean).join('\n\n');
  }
  if (skillId === 'reverse.strings') {
    const items = list(result.items);
    return [
      `${String(result.path)} · ${Number(result.count ?? 0)} strings encontradas${result.truncated ? ' (lista limitada)' : ''}.`,
      items.length ? items.slice(0, 10).map((item) => `• 0x${Number(item.offset ?? 0).toString(16)} [${String(item.encoding)}] ${String(item.value).slice(0, 120)}`).join('\n') : 'Nenhuma string corresponde ao filtro.',
      'Somente bytes imprimíveis; valores podem conter dados sensíveis e nunca saem do núcleo local.',
    ].join('\n\n');
  }
  if (skillId === 'reverse.entropy') {
    const runs = list(result.runs);
    const high = runs.filter((run) => String(run.classification) === 'high').length;
    const low = runs.filter((run) => String(run.classification) === 'low').length;
    return [
      `${String(result.path)} · entropia ${Number(result.fileEntropy ?? 0).toFixed(4)}`,
      `${Number(result.blockCount ?? 0)} blocos de ${Number(result.blockSize ?? 0)} B: ${high} regiões de alta entropia e ${low} de baixa.`,
      'Entropia alta sugere compressão ou cifra; nada foi descompactado ou executado.',
    ].join('\n\n');
  }
  if (skillId === 'reverse.javascript') {
    const target = record(result.target);
    const coverage = record(result.coverage);
    const modules = list(result.modules);
    const unresolved = list(result.unresolved);
    const attention = list(result.facts).filter((fact) => String(fact.severity) === 'attention');
    return [
      `${String(target.path)} · modo ${String(result.mode)} · ${Number(target.files ?? 0)} arquivos · ${bytes(target.bytesRead ?? coverage.bytesRead)}`,
      `${modules.length} módulos, ${list(result.relationships).length} relações resolvidas e ${unresolved.length} pendências.`,
      attention.length ? `Fatos que pedem atenção:\n${attention.slice(0, 6).map((fact) => `• ${String(fact.file)}:${Number(fact.line ?? 0)} ${String(fact.category)}`).join('\n')}` : 'Nenhum fato de risco conhecido foi observado.',
      list(result.entryCandidates).length ? `Entradas candidatas: ${list(result.entryCandidates).slice(0, 5).map((item) => String(item.path)).join(', ')}.` : '',
      'Análise por expressões regulares, sem AST, bundler ou execução. Pacotes e URLs não são seguidos.',
    ].filter(Boolean).join('\n\n');
  }
  if (skillId === 'reverse.compare') {
    const left = record(result.left);
    const right = record(result.right);
    const strings = record(result.strings);
    return [
      `${String(left.path)} ↔ ${String(right.path)}`,
      result.identical ? 'Os arquivos são idênticos byte a byte (mesmo SHA-256).' : `Arquivos diferentes · delta de ${bytes(Math.abs(Number(result.sizeDelta ?? 0)))} · ${result.comparable ? 'mesmo formato' : 'formatos distintos'}.`,
      `Strings amostradas: ${Number(strings.addedCount ?? 0)} adicionadas e ${Number(strings.removedCount ?? 0)} removidas.`,
      'Diferenças estáticas não provam mudança de comportamento. Nada foi executado.',
    ].join('\n\n');
  }
  return 'Análise reversa concluída sem saída textual. Abra a página Reversa para o resultado completo.';
}


function formatLeanChatResult(skillId: string, result: Record<string, unknown>): string {
  const counts = record(result.counts);
  if (skillId === 'lean.ladder') {
    const decision = record(result.decision);
    const obligation = record(result.testObligation);
    const warnings = Array.isArray(result.warnings) ? result.warnings.map(String) : [];
    const items = list(result.rungs).map((rung, index) => `${index + 1}. ${String(rung.label)} — ${String(rung.status)}`);
    return [
      `Decisão: degrau ${Number(decision.rung ?? 0)} — ${String(decision.label ?? 'mínimo necessário')}.`,
      decision.evidence ? `Evidência: ${String(decision.evidence)}.` : '',
      items.length ? `Escada:\n${items.join('\n')}` : '',
      `Teste obrigatório: ${obligation.required ? 'sim' : 'não'}.`,
      warnings.length ? `Avisos:\n${warnings.slice(0, 3).map((warning) => `• ${warning}`).join('\n')}` : '',
      'A escada avalia só o que foi declarado: nenhum arquivo do repositório foi lido.',
    ].filter(Boolean).join('\n\n');
  }
  if (skillId === 'lean.debt') {
    const totals = record(result.totals);
    const rows = list(result.rows);
    return [
      `${Number(totals.markers ?? 0)} marcador(es) de atalho em ${Number(totals.files ?? 0)} arquivo(s); ${Number(totals.noTrigger ?? 0)} sem gatilho.`,
      rows.length ? rows.slice(0, 6).map((row) => `• ${String(row.file)}:${Number(row.line)} — ${String(row.ceiling)}${row.noTrigger ? ' (no-trigger)' : ''}`).join('\n') : 'Nenhum marcador encontrado.',
      'O histórico do Git não é lido; só comentários com o marcador entram no livro.',
    ].join('\n\n');
  }
  const findings = list(result.findings);
  return [
    String(result.verdict ?? 'Análise concluída.'),
    `${Number(counts.must ?? 0)} obrigatório(s), ${Number(counts.should ?? 0)} para corrigir e ${Number(counts.nice ?? 0)} opcional(is).`,
    findings.length ? findings.slice(0, 5).map((finding) => `• ${String(finding.title)} (${String(finding.location)})`).join('\n') : 'Nenhum candidato pelas regras deste nível.',
    'Análise estática: achados são candidatos. Abra Enxuto para as quatro partes de cada achado e os limites.',
  ].join('\n\n');
}

export function formatPythonChatResult(skillId: string, result: Record<string, unknown>): string {
  if (skillId.startsWith('legal.')) return formatLegalChatResult(skillId, result);
  if (skillId.startsWith('reverse.')) return formatReverseChatResult(skillId, result);
  if (skillId.startsWith('lean.')) return formatLeanChatResult(skillId, result);
  if (skillId.startsWith('engineering.')) return String(result.markdown ?? 'Workflow concluído sem saída textual.');
  if (skillId === 'planning.list') {
    const plans = list(result.plans);
    if (!plans.length) return 'Nenhum plano persistente foi encontrado. Abra Planos para simular e confirmar a criação dos três arquivos.';
    return [
      `Encontrei ${plans.length} ${plans.length === 1 ? 'plano' : 'planos'}. Nenhum foi selecionado automaticamente:`,
      plans.slice(0, 10).map((plan) => {
        const gate = typeof plan.gate === 'object' && plan.gate !== null ? plan.gate as Record<string, unknown> : {};
        return `• ${String(plan.planId)} — ${String(plan.title)} · ${plan.invalid ? 'formato inválido' : `${Number(gate.completePhases ?? 0)}/${Number(gate.phaseCount ?? 0)} fases`}`;
      }).join('\n'),
      plans.length > 10 ? `Exibição limitada a 10 de ${plans.length}.` : '',
      'Use “retomar plano ID” ou abra a página Planos.',
    ].filter(Boolean).join('\n\n');
  }
  if (skillId === 'planning.resume') {
    return `${String(result.markdown ?? 'Plano retomado.')}\n\nSomente os três arquivos deste ID foram lidos; nenhum histórico de sessão foi acessado. Abra Planos para revisar ou confirmar uma atualização.`;
  }
  if (skillId === 'planning.gate') return String(result.markdown ?? 'Gate verificado sem executar comandos.');
  if (skillId === 'text.analyze') {
    const terms = list(result.topTerms).slice(0, 3).map((item) => String(item.term ?? '')).filter(Boolean).join(', ');
    return [
      'Análise concluída pela skill Python:',
      `• ${Number(result.words ?? 0)} palavras e ${Number(result.characters ?? 0)} caracteres.`,
      `• ${Number(result.sentences ?? 0)} frases; leitura estimada de ${Number(result.estimatedReadingMinutes ?? 0)} min.`,
      terms ? `• Termos em destaque: ${terms}.` : '',
    ].filter(Boolean).join('\n');
  }
  if (skillId === 'files.list') {
    const files = list(result.files);
    if (!files.length) return 'A área de documentos está vazia. Abra a página Documentos para enviar ou criar um arquivo.';
    return [
      `Encontrei ${files.length} ${files.length === 1 ? 'arquivo' : 'arquivos'} na área isolada:`,
      files.slice(0, 10).map((file) => `• ${String(file.path)} (${Number(file.bytes ?? 0).toLocaleString('pt-BR')} bytes)`).join('\n'),
      files.length > 10 ? `Exibição limitada a 10 de ${files.length}.` : '',
      'Abra Documentos para ler ou baixar os arquivos.',
    ].filter(Boolean).join('\n\n');
  }
  if (skillId === 'document.read') {
    const text = String(result.text ?? '');
    return [
      `${String(result.path)} · ${String(result.format).toUpperCase()} · ${Number(result.bytes ?? 0).toLocaleString('pt-BR')} bytes`,
      text.length > 6_000 ? `${text.slice(0, 6_000)}\n\n[Exibição limitada na conversa.]` : text,
      result.truncated ? 'A extração também foi limitada pelo servidor. Baixe o original na página Documentos.' : 'Abra Documentos para baixar o arquivo original.',
    ].join('\n\n');
  }
  if (skillId === 'meeting.analyze') {
    const speakers = list(result.speakers);
    const actions = Array.isArray(result.actionItems) ? result.actionItems.map(String) : [];
    const decisions = Array.isArray(result.decisions) ? result.decisions.map(String) : [];
    return [
      `Análise textual: ${Number(result.words ?? 0)} palavras, ${Number(result.speakerCount ?? 0)} participantes identificados e ${Number(result.questions ?? 0)} perguntas.`,
      speakers.length ? `Participantes:\n${speakers.slice(0, 6).map((speaker) => `• ${String(speaker.name)}: ${Number(speaker.words ?? 0)} palavras, ${Number(speaker.fillerWords ?? 0)} vícios e ${Number(speaker.hedges ?? 0)} hedges`).join('\n')}` : 'Nenhum participante identificado pelo padrão “Nome: fala”.',
      actions.length ? `Possíveis ações (revisar):\n${actions.slice(0, 5).map((action) => `• ${action}`).join('\n')}` : '',
      decisions.length ? `Possíveis decisões (revisar):\n${decisions.slice(0, 5).map((decision) => `• ${decision}`).join('\n')}` : '',
      String(result.notice ?? 'Análise textual; não é diagnóstico nem transcrição por IA.'),
    ].filter(Boolean).join('\n\n');
  }
  if (skillId === 'changelog.generate') {
    return `${String(result.markdown ?? '')}\n\nChangelog gerado por regras locais, sem IA. Revise antes de publicar.`;
  }
  if (skillId === 'random.pick') {
    const winners = Array.isArray(result.winners) ? result.winners.map(String) : [];
    return `Sorteio concluído com ${String(result.method ?? 'aleatoriedade do servidor')}:\n${winners.map((winner, index) => `${index + 1}. ${winner}`).join('\n')}\n\n${Number(result.eligible ?? 0)} participantes elegíveis; nenhuma lista foi enviada à IA.`;
  }
  if (skillId === 'files.organize') {
    const moves = list(result.moves);
    return [
      `Simulação concluída: ${moves.length} ${moves.length === 1 ? 'movimento previsto' : 'movimentos previstos'}. Nenhum arquivo foi movido ou excluído.`,
      moves.slice(0, 8).map((move) => `• ${String(move.from)} → ${String(move.to)}`).join('\n'),
      moves.length > 8 ? `Exibição limitada a 8 de ${moves.length}.` : '',
      'Para gravar, abra Skills → files.organize, desative a simulação, revise e confirme.',
    ].filter(Boolean).join('\n\n');
  }
  return `Skill Python operacional. Versão ${String(result.python ?? 'desconhecida')} em ${String(result.system ?? 'ambiente local')}. O catálogo e a execução estão respondendo pela API.`;
}
