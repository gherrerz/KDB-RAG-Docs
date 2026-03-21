$baseUrl = 'http://127.0.0.1:8000'

$body = @{
    repo_id = 'mall'
    query = 'cuales son los controller del modulo mall-admin'
    top_n = 60
    top_k = 15
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "$baseUrl/query" -ContentType 'application/json' -Body $body
