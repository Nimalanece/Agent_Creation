$response = Invoke-WebRequest -Uri 'http://localhost:8000/full-analysis?url=https://saucedemo.com' -Method Get -ErrorAction Stop -SkipHttpErrorCheck
Write-Host "Status Code: $($response.StatusCode)"

if ($response.StatusCode -eq 200) {
    $result = $response.Content | ConvertFrom-Json
    
    # Check agent_3_input testcases
    $testcases = $result.agent_1_contract.agent_3_input.test_cases
    Write-Host "Number of testcases: $($testcases.Count)"
    
    if ($testcases.Count -gt 0) {
        $tc = $testcases[0]
        Write-Host "First testcase application_url: $($tc.application_url)"
        Write-Host "First testcase title: $($tc.title)"
        Write-Host "First testcase has expected_results: $(if($tc.expected_results) { 'YES - count: ' + $tc.expected_results.Count } else { 'NO' })"
        Write-Host "First testcase expected_result field: $($tc.expected_result)"
    }
} else {
    Write-Host "Error response:"
    Write-Host $response.Content
}
