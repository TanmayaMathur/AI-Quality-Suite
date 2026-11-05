function result(pass, reason) {
  return { pass, score: Number(pass), reason };
}

module.exports = (output, { vars }) => {
  const reference = JSON.parse(vars.reference);
  if (reference.category === 'unanswerable') {
    return result(output.outcome === 'abstained' && output.sources.length === 0, 'Expected abstention');
  }
  if (output.outcome !== 'answered') return result(false, 'Expected a cited public answer');
  const wanted = new Set(reference.source_documents);
  if (!output.sources.some((source) => wanted.has(source.document_id))) {
    return result(false, 'No expected document was cited');
  }
  if (!reference.must_include.every((term) => output.answer.toLowerCase().includes(term.toLowerCase()))) {
    return result(false, 'Expected fact marker missing');
  }
  return result(true, 'Outcome, cited source, and fact markers match');
};
