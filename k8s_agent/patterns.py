import re
from typing import List, Dict, Any, Optional
from .models import Severity


class FailureSignature:
    """Defines a pattern signature for detecting Kubernetes anomalies."""

    def __init__(
        self,
        signature_id: str,
        category: str,
        title: str,
        severity: Severity,
        patterns: List[str],
        root_cause_weight: int,
        description: str,
        immediate_action: str,
        suggested_kubectl: Optional[str] = None,
        prevention_tip: Optional[str] = None,
    ):
        self.signature_id = signature_id
        self.category = category
        self.title = title
        self.severity = severity
        self.patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
        self.root_cause_weight = root_cause_weight
        self.description = description
        self.immediate_action = immediate_action
        self.suggested_kubectl = suggested_kubectl
        self.prevention_tip = prevention_tip

    def matches(self, text: str) -> Optional[str]:
        """Returns the matched substring or pattern description if found."""
        for regex in self.patterns:
            m = regex.search(text)
            if m:
                return m.group(0)
        return None


# Catalog of Kubernetes failure modes ordered by specificity
K8S_SIGNATURES: List[FailureSignature] = [
    FailureSignature(
        signature_id="SIG_OOM_KILL",
        category="OOM_KILL",
        title="Out of Memory (OOMKilled) Detected",
        severity=Severity.CRITICAL,
        patterns=[
            r"oomkilled",
            r"exit code 137\b",
            r"command terminated with exit code 137",
            r"cgroup out of memory",
            r"java\.lang\.OutOfMemoryError",
            r"Killed process \d+.*total-vm:.*anon-rss:",
            r"Container .* was terminated \(reason: 'OOMKilled'\)",
        ],
        root_cause_weight=95,
        description="The container exceeded its configured cgroup memory limit or node memory was exhausted, causing the Linux OOM Killer to terminate the process (Exit code 137).",
        immediate_action="Increase container memory limits in the deployment spec and inspect heap/memory consumption.",
        suggested_kubectl="kubectl top pod <pod-name> --containers\nkubectl get pod <pod-name> -o jsonpath='{.status.containerStatuses[*].lastState.terminated}'",
        prevention_tip="Configure appropriate requests and limits based on observed peak loads, and implement Vertical Pod Autoscaler (VPA) or profilers to detect memory leaks.",
    ),
    FailureSignature(
        signature_id="SIG_CONFIG_SECRET_MISSING",
        category="CONFIG_ERROR",
        title="Missing ConfigMap or Secret Dependency",
        severity=Severity.CRITICAL,
        patterns=[
            r"CreateContainerConfigError",
            r"configmap \".*?\" not found",
            r"secret \".*?\" not found",
            r"references non-existent (configmap|secret)",
            r"Failed to populate volume: .*secret.* not found",
            r"KeyError: '.*_(?:KEY|SECRET|PASSWORD|CONFIG)'",
        ],
        root_cause_weight=90,
        description="Container initialization failed because a required ConfigMap, Secret, or environment variable reference does not exist in the namespace.",
        immediate_action="Verify that all referenced ConfigMaps and Secrets are created and spelled correctly in the target namespace.",
        suggested_kubectl="kubectl get secrets,configmaps -n <namespace>\nkubectl describe pod <pod-name>",
        prevention_tip="Use Helm or Kustomize validation dry-runs in CI/CD pipelines to ensure all dependent resources exist before deployment.",
    ),
    FailureSignature(
        signature_id="SIG_IMAGE_PULL_FAILURE",
        category="IMAGE_PULL",
        title="Container Image Pull Failure",
        severity=Severity.HIGH,
        patterns=[
            r"ImagePullBackOff",
            r"ErrImagePull",
            r"manifest for .* not found",
            r"manifest unknown",
            r"pull access denied",
            r"repository .* does not exist or may require 'docker login'",
            r"rpc error: code = Unknown desc = Error response from daemon: unauthorized",
            r"Back-off pulling image",
        ],
        root_cause_weight=90,
        description="The kubelet cannot pull the specified container image due to an invalid image tag, non-existent repository, or missing/expired registry credentials.",
        immediate_action="Check image tag and repository path in the container spec, and verify imagePullSecrets.",
        suggested_kubectl="kubectl describe pod <pod-name> | grep -A 5 -E '(Events:|Image:)'",
        prevention_tip="Pin images to immutable digest hashes or specific semantic versions; avoid relying on 'latest' tags and automate secret rotation.",
    ),
    FailureSignature(
        signature_id="SIG_DATABASE_UNREACHABLE",
        category="DATABASE_OUTAGE",
        title="Database / Upstream Datastore Connection Failure",
        severity=Severity.HIGH,
        patterns=[
            r"could not connect to server: Connection refused",
            r"psycopg2\.OperationalError",
            r"MongoNetworkError",
            r"dial tcp .*:5432: connect: connection refused",
            r"dial tcp .*:3306: connect: connection refused",
            r"dial tcp .*:6379: connect: connection refused",
            r"redis\.exceptions\.ConnectionError",
            r"too many connections",
            r"pool exhausted",
            r"failed to acquire connection from pool",
        ],
        root_cause_weight=85,
        description="The application is unable to establish or maintain a connection to its backend database or cache. This often triggers cascading readiness probe failures.",
        immediate_action="Check database pod/service status, verify network reachability, and check for connection pool exhaustion.",
        suggested_kubectl="kubectl get svc,endpoints <db-service-name>\nkubectl logs -l app=<db-app>",
        prevention_tip="Implement exponential backoff retries, connection pooling with circuit breakers, and database connection monitors.",
    ),
    FailureSignature(
        signature_id="SIG_DNS_RESOLUTION_FAILURE",
        category="NETWORK_DNS",
        title="CoreDNS / Cluster DNS Resolution Failure",
        severity=Severity.HIGH,
        patterns=[
            r"lookup [a-zA-Z0-9_\-\.]+ on .*:53: no such host",
            r"Temporary failure in name resolution",
            r"dial udp .*:53: i/o timeout",
            r"server can't find .*: NXDOMAIN",
            r"getaddrinfo ENOTFOUND",
            r"EAI_AGAIN",
        ],
        root_cause_weight=85,
        description="The application failed to resolve a domain name or internal Kubernetes service FQDN via CoreDNS.",
        immediate_action="Inspect CoreDNS pods and check if the queried service exists in the expected namespace.",
        suggested_kubectl="kubectl -n kube-system get pods -l k8s-app=kube-dns\nkubectl -n kube-system logs -l k8s-app=kube-dns --tail=50",
        prevention_tip="Ensure Fully Qualified Domain Names (e.g. `<svc>.<namespace>.svc.cluster.local`) are used for cross-namespace communication and enable NodeLocal DNSCache.",
    ),
    FailureSignature(
        signature_id="SIG_RBAC_FORBIDDEN",
        category="RBAC_PERMISSION",
        title="Kubernetes RBAC Authorization Denied (403 Forbidden)",
        severity=Severity.HIGH,
        patterns=[
            r"is forbidden: User \".*?\" cannot .*? in the namespace",
            r"system:serviceaccount:.*? cannot list resource",
            r"HTTP status 403 Forbidden",
            r"RBAC: access denied",
            r"User \".*?\" cannot get resource \".*?\" in API group",
        ],
        root_cause_weight=85,
        description="The pod's ServiceAccount lacks sufficient RBAC Role or ClusterRole permissions to perform requested API server operations.",
        immediate_action="Inspect the pod's serviceAccountName and test permissions using `kubectl auth can-i`.",
        suggested_kubectl="kubectl auth can-i <verb> <resource> --as=system:serviceaccount:<namespace>:<serviceaccount-name>\nkubectl describe rolebinding,clusterrolebinding -n <namespace>",
        prevention_tip="Follow the principle of least privilege by binding specific Roles with precise verbs and resourceNames.",
    ),
    FailureSignature(
        signature_id="SIG_TLS_CERT_FAILURE",
        category="TLS_ERROR",
        title="TLS / SSL Certificate Verification Failure",
        severity=Severity.HIGH,
        patterns=[
            r"x509: certificate signed by unknown authority",
            r"certificate has expired or is not yet valid",
            r"SSL: CERTIFICATE_VERIFY_FAILED",
            r"tls: bad certificate",
            r"remote error: tls: internal error",
            r"admission webhook .* failed to call webhook: .* x509: certificate signed by unknown authority",
        ],
        root_cause_weight=80,
        description="A TLS handshake failed due to an expired certificate, untrusted CA root, or mismatched hostname.",
        immediate_action="Check the expiration date and issuer of the TLS secret or admission webhook CA bundle.",
        suggested_kubectl="kubectl get certificate -A\nopenssl x509 -in <cert-file> -text -noout | grep -A 2 'Validity'",
        prevention_tip="Deploy cert-manager with automated renewal alerts and Prometheus metrics for expiring certificates.",
    ),
    FailureSignature(
        signature_id="SIG_STORAGE_VOLUME_FAILURE",
        category="STORAGE_ERROR",
        title="Storage Volume Mount or Disk Exhaustion Failure",
        severity=Severity.HIGH,
        patterns=[
            r"no space left on device",
            r"FailedMount",
            r"MountVolume\.SetUp failed",
            r"Multi-Attach error for volume",
            r"volume .* is already exclusively attached to one node",
            r"permission denied on volume",
        ],
        root_cause_weight=80,
        description="The container could not mount its PersistentVolume, or the underlying node/volume filesystem has run out of disk space or inodes.",
        immediate_action="Check PVC status and node disk utilization.",
        suggested_kubectl="kubectl get pvc,pv\nkubectl describe pod <pod-name> | grep -A 10 Volumes",
        prevention_tip="Set storage requests appropriately with volume expansion enabled (`allowVolumeExpansion: true`), and configure log rotation to prevent root disk filling.",
    ),
    FailureSignature(
        signature_id="SIG_PROBE_FAILURE",
        category="PROBE_FAILURE",
        title="Liveness / Readiness / Startup Probe Failed",
        severity=Severity.MEDIUM,
        patterns=[
            r"Liveness probe failed: HTTP probe failed with statuscode: 500",
            r"Readiness probe failed: HTTP probe failed with statuscode: 500",
            r"Startup probe failed: HTTP probe failed with statuscode: 500",
            r"Readiness probe failed: connection refused",
            r"Liveness probe failed: connection refused",
            r"probe failed: timeout",
            r"Container failed liveness probe, will be restarted",
            r"Unhealthy.*Readiness probe failed",
            r"Unhealthy.*Liveness probe failed",
        ],
        root_cause_weight=50,
        description="The kubelet probe check failed. A failing readiness probe removes the pod from service endpoints; a failing liveness probe causes the kubelet to restart the container.",
        immediate_action="Check why the health endpoint returned an error (often due to upstream dependency or slow boot).",
        suggested_kubectl="kubectl describe pod <pod-name> | grep -A 8 -E '(Liveness:|Readiness:)'",
        prevention_tip="Ensure health check endpoints only test critical local dependencies and increase `initialDelaySeconds` or use `startupProbe` for slow-starting applications.",
    ),
    FailureSignature(
        signature_id="SIG_APPLICATION_PANIC",
        category="APPLICATION_PANIC",
        title="Application Fatal Exception or Panic",
        severity=Severity.HIGH,
        patterns=[
            r"panic: runtime error:",
            r"SIGSEGV: segmentation violation",
            r"NullPointerException",
            r"Traceback \(most recent call last\):",
            r"fatal error: concurrent map read and map write",
            r"UnhandledPromiseRejectionWarning",
            r"Uncaught TypeError:",
        ],
        root_cause_weight=75,
        description="The application encountered an unhandled exception, null pointer dereference, or fatal runtime panic.",
        immediate_action="Inspect the detailed stack trace to isolate the faulting module, file, and line.",
        suggested_kubectl="kubectl logs <pod-name> --previous --tail=100",
        prevention_tip="Implement comprehensive global exception handlers and add automated unit/integration test coverage.",
    ),
    FailureSignature(
        signature_id="SIG_CRASH_LOOP_BACKOFF",
        category="CRASH_LOOP",
        title="Pod in CrashLoopBackOff",
        severity=Severity.HIGH,
        patterns=[
            r"CrashLoopBackOff",
            r"Back-off restarting failed container",
            r"Back-off \d+[smh]+ restarting failed container",
            r"container .* in pod .* is in CrashLoopBackOff",
        ],
        root_cause_weight=40,  # Typically a symptom of underlying crashes, OOM, or missing config
        description="The container process repeatedly exited with a non-zero exit code. Kubelet is applying an exponential restart delay.",
        immediate_action="Investigate the root cause in the previous container instance logs.",
        suggested_kubectl="kubectl logs <pod-name> -c <container-name> --previous",
        prevention_tip="Fix the underlying error causing process termination (e.g., config error, crash, or OOM).",
    ),
    FailureSignature(
        signature_id="SIG_NETWORK_TIMEOUT",
        category="NETWORK_TIMEOUT",
        title="Network Gateway / Upstream Connection Timeout",
        severity=Severity.MEDIUM,
        patterns=[
            r"context deadline exceeded",
            r"upstream connect error or disconnect/reset before headers",
            r"504 Gateway Timeout",
            r"502 Bad Gateway",
            r"connection reset by peer",
            r"dial tcp: i/o timeout",
        ],
        root_cause_weight=55,
        description="A network call or proxy upstream request timed out or received an invalid response.",
        immediate_action="Verify downstream pod responsiveness and check NetworkPolicies or Envoy sidecar logs.",
        suggested_kubectl="kubectl get endpoints <service-name>\nkubectl logs <ingress-controller-pod>",
        prevention_tip="Review timeouts across ingress controllers, mesh proxies, and clients to ensure appropriate cascading deadline values.",
    ),
]
