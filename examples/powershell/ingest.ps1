$baseUrl = 'http://127.0.0.1:8000'

$body = @{
    provider = 'github'
    repo_url = 'https://github.com/macrozheng/mall.git'
    branch = 'main'
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "$baseUrl/repos/ingest" -ContentType 'application/json' -Body $body
