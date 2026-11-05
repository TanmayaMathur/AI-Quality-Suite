param(
    [ValidateSet('both', 'deepeval', 'ragas', 'deterministic')]
    [string]$Framework = 'both',
    [ValidateRange(1, 5)][int]$Repetitions = 3,
    [ValidateRange(1, 66)][int]$MaxCases = 12,
    [string]$JudgeModel = 'qwen2.5:3b',
    [string]$BaselineFile,
    [string]$PromptfooReport,
    [switch]$RequireBaseline
)
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-AqsPython
Push-Location $AqsRoot
try {
    $options = @('--framework', $Framework, '--repetitions', "$Repetitions", '--max-cases', "$MaxCases", '--judge-model', $JudgeModel)
    if ($RequireBaseline) { $options += '--require-baseline' }
    if ($BaselineFile) { $options += @('--baseline-file', $BaselineFile) }
    if ($PromptfooReport) { $options += @('--promptfoo-json', $PromptfooReport) }
    & $AqsPython -m evaluation.runner @options
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
