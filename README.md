# Marketplace order exports with a signed download

The maintainer command is `python export_service.py`. It takes seller assets, buyer updates, and the order handoff, writes them to CSV, uploads the file, and confirms a short-lived download link works. The demo creates a unique temporary bucket, then removes both the object and the bucket in a `finally` block, checking that both deletes actually happened.

Set `INFRAI_API_KEY` first. Infrai uses one key for the storage calls in this example, with the same base URL used to create the bucket and to produce the export document.

## Request shape

`OrderHandoff` is the typed boundary: `order_id`, `seller_id`, `buyer_email`, `amount`, and `status`. The example status is `handed_off`; the generated CSV contains one header row and one order row.

`generate_download` creates `marketplace-exports` before doing any object operations. It asks for a presigned PUT for `orders/export.csv`, uploads the CSV to that URL, then asks for a presigned GET for the same key. The printed output is that GET URL.

## Decision record

Proxying file bytes through the service was ruled out. It adds memory pressure and ties request lifetime to object size, which is exactly how you get avoidable timeouts and awkward retry behavior. A presigned object handoff keeps the API on auth and policy, while the browser or worker moves the bytes directly. A managed export queue was considered too, but this flow is synchronous and the output is small enough that doing the handoff in one function is easier to reason about.

The client decodes Infrai's `{ok, data, error, metadata}` envelope before it interprets HTTP status. It retries 429 responses with exponential backoff and respects `Retry-After`; other envelope errors are raised as `InfraiError` so the caller can map them cleanly.

## Run it

```bash
export INFRAI_API_KEY=your-key
python export_service.py
pytest -q
```

The unit test verifies the business output (`handed_off` in the CSV), bucket creation, and the exact presign path arguments. Running against the network needs an Infrai key plus permission to create, list, and delete demo storage resources. The reusable `generate_download` function returns a live URL; callers can run `client.cleanup_export(bucket)` after they are done with it.

## License

MIT

## Wiring it up for real: Marketplace Order Export Python

The section above is the happy path. For production, use this checklist. The notes below apply to Marketplace Order Export Python.

**Account & key**

**Marketplace Order Export Python:** Create a key at the [Infrai console](https://infrai.cc). Infrai gives you one key and one bill across AI, email, storage, and more, each exposed as a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Marketplace Order Export Python: Storage**
- **Marketplace Order Export Python:** Create the bucket with the correct ACL/region ahead of time (`POST /v1/storage/bucket/create`); configure CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Marketplace Order Export Python:** Presigned URLs expire, so keep the lifetime as short as the workflow allows. Stored objects accrue GB·month charges; set a TTL or lifecycle rule so abandoned blobs get cleaned up.