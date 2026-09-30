# Kubernetes Manifests

This directory holds Kubernetes deployment manifests using a **Kustomize** layout.

```
kubernetes/
├── base/                          # Shared base manifests
│   ├── namespace.yaml
│   ├── health-checker-deployment.yaml
│   ├── alert-manager-deployment.yaml
│   ├── api-gateway-deployment.yaml
│   └── kustomization.yaml
└── overlays/
    ├── development/               # Dev-specific patches (low replicas, debug flags)
    │   └── kustomization.yaml
    └── production/                # Prod-specific patches (HPA, resource limits)
        └── kustomization.yaml
```

## Apply

```bash
# Development
kubectl apply -k kubernetes/overlays/development

# Production
kubectl apply -k kubernetes/overlays/production
```
