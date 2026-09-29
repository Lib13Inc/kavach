# deploy

One directory per thing we deploy and where it runs.

| Path | What | Where |
| --- | --- | --- |
| `web/cloudflare/` | Project site (the Pitch & Spec) | Cloudflare Worker, https://kavach.lib13.com |
| `homelab/` | The full demo stack (gateway, sandbox, eBPF guard, local model) | VM on the Proxmox host minipve |
| `crusoe/` | The same demo, with Crusoe's hosted Qwen as the model | Crusoe Cloud VM + Crusoe Managed Inference |
| `aws/` (planned) | The same demo on EC2 (m8i/c8i, nested virt) | AWS |
