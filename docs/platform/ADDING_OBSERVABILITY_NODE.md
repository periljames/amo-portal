# Adding an observability node or VM

Use this procedure for every additional application/database/worker node that must appear in Platform Operations.

## 1. Install the agent

On the new Ubuntu node:

```bash
cd ops/observability
sudo ./scripts/install-ubuntu.sh \
  --role agent \
  --bind-address <private-node-address> \
  --hub-address <private-observability-hub-address> \
  --cluster-id <cluster-id> \
  --environment production
```

Do not use `0.0.0.0` or `::`. Expose agent ports only on the approved private management network.

## 2. Register the node with Prometheus discovery

On the hub:

```bash
./scripts/add-node.sh \
  --node-id <stable-node-id> \
  --address <private-node-address>
```

For an all-in-one Docker deployment, explicit service targets may be used:

```bash
./scripts/add-node.sh \
  --node-id <stable-node-id> \
  --node-exporter-target node-exporter:9100 \
  --cadvisor-target cadvisor:8080
```

Registration is file-based and does not require hand-editing `prometheus.yml`.

## 3. Verify ingestion

Run:

```bash
./scripts/verify.sh
```

Then confirm in the Superadmin Control Center:

- node appears under Infrastructure;
- CPU, memory and load are present;
- network ingress/egress and errors are present;
- filesystem/inode metrics are present;
- cAdvisor container series appear;
- historical node ranges return data rather than only current values.

## 4. Validate failure behavior

Temporarily stop only the node agent and confirm:

- the tenant API remains healthy;
- the Operations UI marks telemetry stale/unavailable;
- last-known values remain clearly marked stale;
- Alertmanager/Prometheus detect the missing target where configured.

Do not perform this test by stopping tenant application services.

## 5. Remove a node

On the hub:

```bash
./scripts/remove-node.sh --node-id <stable-node-id>
```

Retain incident/change evidence if the node was removed because of a production event.
