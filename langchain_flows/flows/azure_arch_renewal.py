"""
Azure Solutions Architect Expert Certification Renewal
"""

# Renewal landing page
RENEWAL_PAGE = "https://learn.microsoft.com/en-us/credentials/certifications/azure-solutions-architect/renew/"

# Base collection URLs
COLLECTION_BASE_URLS = [
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-relational-data/?ns-enrollment-type=Collection",
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-non-relational-data/?ns-enrollment-type=Collection", 
    "https://learn.microsoft.com/en-us/training/modules/describe-high-availability-disaster-recovery-strategies/?ns-enrollment-type=Collection",
    "https://learn.microsoft.com/en-us/training/modules/design-compute-solution/?ns-enrollment-type=Collection",
    "https://learn.microsoft.com/en-us/training/modules/design-application-architecture/?ns-enrollment-type=Collection",
    "https://learn.microsoft.com/en-us/training/modules/design-network-solutions/?ns-enrollment-type=Collection",
    "https://learn.microsoft.com/en-us/training/modules/design-data-integration/?ns-enrollment-type=Collection",
]

# Collection Child Page URLs

# 1. Design a data storage solution for relational data (11 units)
RELATIONAL_DATA_URLS = [
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-relational-data/1-introduction",
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-relational-data/2-design-for-azure-sql-database",
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-relational-data/3-design-for-azure-sql-managed-instance",
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-relational-data/4-design-for-sql-server-azure",
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-relational-data/5-recommend-database-scalability",
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-relational-data/6-recommend-database-availability",
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-relational-data/7-design-security-for-data-at-rest-data-transmission-data-use",
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-relational-data/8-design-for-azure-sql-edge",
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-relational-data/9-design-for-azure-cosmos",
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-relational-data/10-knowledge-check",
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-relational-data/11-summary-resources",
]

# 2. Design a data storage solution for non-relational data (10 units)
NON_RELATIONAL_DATA_URLS = [
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-non-relational-data/1-introduction",
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-non-relational-data/2-design-for-data-storage",
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-non-relational-data/3-design-for-azure-storage-accounts",
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-non-relational-data/4-design-for-data-redundancy",
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-non-relational-data/5-design-for-azure-blob-storage",
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-non-relational-data/6-design-for-azure-files",
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-non-relational-data/7-design-for-azure-disk-solutions",
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-non-relational-data/8-design-for-storage-security",
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-non-relational-data/9-knowledge-check",
    "https://learn.microsoft.com/en-us/training/modules/design-data-storage-solution-for-non-relational-data/10-summary-resources",
]


# 3. Describe high availability and disaster recovery strategies (9 units) - FROM PROVIDED SAMPLE
HADR_URLS = [
    "https://learn.microsoft.com/en-us/training/modules/describe-high-availability-disaster-recovery-strategies/1-introduction",
    "https://learn.microsoft.com/en-us/training/modules/describe-high-availability-disaster-recovery-strategies/2-describe-recovery-time-objective-recovery-point-objective",
    "https://learn.microsoft.com/en-us/training/modules/describe-high-availability-disaster-recovery-strategies/3-explore-high-availability-disaster-recovery-options",
    "https://learn.microsoft.com/en-us/training/modules/describe-high-availability-disaster-recovery-strategies/4-describe-azure-high-availability-disaster-recovery-features",
    "https://learn.microsoft.com/en-us/training/modules/describe-high-availability-disaster-recovery-strategies/5-describe-high-availability-disaster-recovery-options",
    "https://learn.microsoft.com/en-us/training/modules/describe-high-availability-disaster-recovery-strategies/6-explore-iaas-high-availability-disaster-recovery-solution",
    "https://learn.microsoft.com/en-us/training/modules/describe-high-availability-disaster-recovery-strategies/7-describe-hybrid-solutions",
    "https://learn.microsoft.com/en-us/training/modules/describe-high-availability-disaster-recovery-strategies/8-knowledge-check",
    "https://learn.microsoft.com/en-us/training/modules/describe-high-availability-disaster-recovery-strategies/9-summary",
]

# 4. Design an Azure compute solution (11 units)
COMPUTE_SOLUTION_URLS = [
    "https://learn.microsoft.com/en-us/training/modules/design-compute-solution/1-introduction",
    "https://learn.microsoft.com/en-us/training/modules/design-compute-solution/2-choose-compute-service",
    "https://learn.microsoft.com/en-us/training/modules/design-compute-solution/3-design-for-azure-virtual-machine-solutions",
    "https://learn.microsoft.com/en-us/training/modules/design-compute-solution/4-design-for-azure-batch-solutions",
    "https://learn.microsoft.com/en-us/training/modules/design-compute-solution/5-design-for-azure-app-services-solutions",
    "https://learn.microsoft.com/en-us/training/modules/design-compute-solution/6-design-for-azure-container-instances-solutions",
    "https://learn.microsoft.com/en-us/training/modules/design-compute-solution/7-design-for-azure-kubernetes-solutions",  # CORRECTED - was causing 404
    "https://learn.microsoft.com/en-us/training/modules/design-compute-solution/8-design-for-azure-functions-solutions",
    "https://learn.microsoft.com/en-us/training/modules/design-compute-solution/9-design-for-logic-app-solutions",  # CORRECTED - was causing 404
    "https://learn.microsoft.com/en-us/training/modules/design-compute-solution/10-knowledge-check",
    "https://learn.microsoft.com/en-us/training/modules/design-compute-solution/11-summary-resources",
]

# 5. Design an application architecture (11 units)
APPLICATION_ARCHITECTURE_URLS = [
    "https://learn.microsoft.com/en-us/training/modules/design-application-architecture/1-introduction",
    "https://learn.microsoft.com/en-us/training/modules/design-application-architecture/2-describe-message-event-scenarios",
    "https://learn.microsoft.com/en-us/training/modules/design-application-architecture/3-design-messaging-solution",
    "https://learn.microsoft.com/en-us/training/modules/design-application-architecture/4-design-event-hub-messaging-solution",
    "https://learn.microsoft.com/en-us/training/modules/design-application-architecture/5-design-event-driven-solution",
    "https://learn.microsoft.com/en-us/training/modules/design-application-architecture/6-design-caching-solution",
    "https://learn.microsoft.com/en-us/training/modules/design-application-architecture/7-design-api-integration",
    "https://learn.microsoft.com/en-us/training/modules/design-application-architecture/8-design-automated-app-deployment-solution",
    "https://learn.microsoft.com/en-us/training/modules/design-application-architecture/9-configuration-management-solution",
    "https://learn.microsoft.com/en-us/training/modules/design-application-architecture/10-knowledge-check",
    "https://learn.microsoft.com/en-us/training/modules/design-application-architecture/11-summary-resources",
]

# 6. Design network solutions (10 units)
NETWORK_SOLUTIONS_URLS = [
    "https://learn.microsoft.com/en-us/training/modules/design-network-solutions/1-introduction",
    "https://learn.microsoft.com/en-us/training/modules/design-network-solutions/2-recommend-network-architecture-solution-based-workload-requirements",
    "https://learn.microsoft.com/en-us/training/modules/design-network-solutions/3-design-patterns-for-azure-network-connectivity-services",
    "https://learn.microsoft.com/en-us/training/modules/design-network-solutions/4-design-outbound-connectivity-routing",
    "https://learn.microsoft.com/en-us/training/modules/design-network-solutions/5-design-for-premises-connectivity-to-azure-virtual-networks",
    "https://learn.microsoft.com/en-us/training/modules/design-network-solutions/6-choose-application-delivery-service",
    "https://learn.microsoft.com/en-us/training/modules/design-network-solutions/7-design-for-application-delivery-services",
    "https://learn.microsoft.com/en-us/training/modules/design-network-solutions/8-design-for-application-protection-services",
    "https://learn.microsoft.com/en-us/training/modules/design-network-solutions/9-knowledge-check",
    "https://learn.microsoft.com/en-us/training/modules/design-network-solutions/10-summary-resources",
]

# 7. Design data integration (9 units)  
DATA_INTEGRATION_URLS = [
    "https://learn.microsoft.com/en-us/training/modules/design-data-integration/1-introduction",
    "https://learn.microsoft.com/en-us/training/modules/design-data-integration/2-solution-azure-data-factory",
    "https://learn.microsoft.com/en-us/training/modules/design-data-integration/3-solution-azure-data-lake",
    "https://learn.microsoft.com/en-us/training/modules/design-data-integration/4-solution-azure-data-brick",
    "https://learn.microsoft.com/en-us/training/modules/design-data-integration/5-solution-azure-synapse-analytics",
    "https://learn.microsoft.com/en-us/training/modules/design-data-integration/6-design-strategy-for-hot-warm-cold-data-path",
    "https://learn.microsoft.com/en-us/training/modules/design-data-integration/7-design-azure-stream-analytics-solution-for-data-analysis",
    "https://learn.microsoft.com/en-us/training/modules/design-data-integration/8-knowledge-check",
    "https://learn.microsoft.com/en-us/training/modules/design-data-integration/9-summary-resources",
]
