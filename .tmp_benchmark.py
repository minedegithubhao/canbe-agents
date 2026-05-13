import asyncio
import json
import httpx

BASE = 'http://127.0.0.1:8811'
EVAL_SET_ID = 'eval_20260513'

async def run_once(case_concurrency, commit_batch_size):
    payload = {
        'configured_k': 5,
        'retrieval_top_n': 20,
        'similarity_threshold': 0.72,
        'rerank_enabled': True,
        'case_concurrency_override': case_concurrency,
        'commit_batch_size_override': commit_batch_size,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        start = await client.post(f'{BASE}/admin/eval-sets/{EVAL_SET_ID}/runs/start', json=payload)
        start.raise_for_status()
        run_id = start.json()['run_id']
        for _ in range(120):
            await asyncio.sleep(3)
            response = await client.get(f'{BASE}/admin/eval-runs/{run_id}')
            response.raise_for_status()
            data = response.json()
            if data.get('status') == 'completed':
                return {
                    'run_id': run_id,
                    'case_concurrency': case_concurrency,
                    'commit_batch_size': commit_batch_size,
                    'summary': data.get('summary'),
                    'timing': data.get('timing'),
                }
        raise RuntimeError(f'run {run_id} did not complete in time')

async def main():
    results = []
    results.append(await run_once(5, 5))
    results.append(await run_once(8, 5))
    print(json.dumps(results, ensure_ascii=False, indent=2))

asyncio.run(main())
