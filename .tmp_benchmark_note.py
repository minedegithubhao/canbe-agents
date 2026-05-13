import asyncio
import json
from pathlib import Path
import httpx

BASE = 'http://127.0.0.1:8811'
EVAL_SET_ID = 'eval_20260513'

async def run_once(concurrency: int, commit_batch: int):
    payload = {
        'configured_k': 5,
        'retrieval_top_n': 20,
        'similarity_threshold': 0.72,
        'rerank_enabled': True,
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
                    'status': data.get('status'),
                    'summary': data.get('summary'),
                    'timing': data.get('timing'),
                    'progress': data.get('progress'),
                }
        raise RuntimeError(f'run {run_id} did not complete in time')

async def main():
    print('This script only polls existing server-side config. Override is not yet supported via API.')

if __name__ == '__main__':
    asyncio.run(main())
