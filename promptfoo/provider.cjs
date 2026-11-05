module.exports = class LocalRagProvider {
  id() { return 'local-lumenvale-rag'; }

  async callApi(prompt, context) {
    try {
      const response = await fetch('http://127.0.0.1:8000/ask', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ question: context.vars.question, prompt_version: prompt.trim() }),
        signal: AbortSignal.timeout(120_000),
      });
      if (!response.ok) return { error: 'RAG HTTP ' + response.status };
      const answer = await response.json();
      return { output: answer, tokenUsage: {
        prompt: answer.input_tokens ?? undefined,
        completion: answer.output_tokens ?? undefined,
      } };
    } catch (error) {
      return { error: 'RAG request ' + error.name };
    }
  }
};
