@description('Environment name used for naming and tagging.')
@allowed([
  'dev'
  'test'
  'prod'
])
param environment string = 'dev'

@description('Azure region for the serverless foundation.')
param location string = resourceGroup().location

@description('Azure region for Document Intelligence when deploying a new account.')
param documentIntelligenceLocation string = location

@description('Azure region for Azure OpenAI when deploying a new account.')
param openAILocation string = location

@description('Deploy Cosmos DB review storage for the queue-backed manual review APIs.')
param deployCosmos bool = true

@description('Deploy Azure SQL resources for account matching.')
param deploySql bool = false

@description('Deploy Azure AI resources for Document Intelligence and Azure OpenAI.')
param deployAiServices bool = false

@description('Deploy the in-template Flex Consumption Function App resource.')
param deployFunctionApp bool = false

@description('Enable Azure Storage SFTP and local-user access on the document landing storage account.')
param enableStorageSftp bool = false

@description('Deploy a dedicated public static website storage account for the HR-safe simulation site.')
param deployPublicSimulationSite bool = false

@description('Deploy Azure Front Door for the public simulation site.')
param deployPublicFrontDoor bool = false

@description('Deploy a private App Service host for the Microsoft-auth-only live admin site.')
param deployPrivateLiveSite bool = false

@description('Custom domain hostname to prepare for the public simulation site, such as www.contoso.com.')
param publicSimulationCustomDomainName string = ''

@description('Associate the prepared public simulation custom domain with the Front Door route after DNS validation succeeds.')
param associatePublicSimulationCustomDomain bool = false

@description('Custom domain hostname to prepare for the private live admin site, such as admin.contoso.com.')
param privateLiveCustomDomainName string = ''

@description('Azure region for the private live admin site when the shared backend region does not have App Service quota.')
param privateLiveLocation string = location

@description('Existing Document Intelligence account name to reuse instead of creating a new one.')
param existingDocumentIntelligenceAccountName string = ''

@description('Existing Azure OpenAI account name to reuse instead of creating a new one.')
param existingOpenAIAccountName string = ''

@description('Deploy Azure Service Bus queues for the legacy review and ingestion publisher paths.')
param deployServiceBus bool = true

type QueueNames = {
  ingestion: string
  review: string
}

@description('Service Bus queue names used by orchestration and manual review.')
param queueNames QueueNames = {
  ingestion: 'document-ingestion'
  review: 'manual-review'
}

type ContainerNames = {
  processed: string
  quarantine: string
  raw: string
}

type BlobLifecycleRetentionDays = {
  functionReleases: int
  processed: int
  quarantine: int
  raw: int
}

@description('Blob containers used for raw, processed, and quarantined documents.')
param containerNames ContainerNames = {
  processed: 'processed-documents'
  quarantine: 'quarantine-documents'
  raw: 'raw-documents'
}

@description('Blob container used to store Function App deployment packages when Flex Consumption is used.')
param functionDeploymentContainerName string = 'function-releases'

@minValue(40)
@maxValue(1000)
@description('Maximum scale-out instance count for the Flex Consumption Function App.')
param functionMaximumInstanceCount int = 100

@allowed([
  2048
  4096
])
@description('Per-instance memory size, in MB, for the Flex Consumption Function App.')
param functionInstanceMemoryMB int = 2048

@description('Enable blob lifecycle deletion policies for the landing storage account.')
param enableBlobLifecyclePolicy bool = true

@description('Retention windows, in days, for landing-storage containers.')
param blobLifecycleRetentionDays BlobLifecycleRetentionDays = {
  functionReleases: 30
  processed: 90
  quarantine: 60
  raw: 30
}

@description('Cosmos DB database name used for workflow state.')
param cosmosDatabaseName string = 'docintel'

@description('Cosmos DB container name used for persisted review items.')
param cosmosReviewContainerName string = 'review-items'

@description('Azure SQL login used for the account master database when deploySql is enabled.')
param sqlAdministratorLogin string = 'docinteladmin'

@secure()
@description('Azure SQL administrator password when deploySql is enabled.')
param sqlAdministratorPassword string = ''

@description('Azure SQL database name used for account master records.')
param sqlDatabaseName string = 'docintel'

@description('Azure SQL table name that stores account master records.')
param sqlAccountTableName string = 'dbo.AccountMaster'

@description('Number of candidate rows to inspect during account matching.')
param sqlLookupTopN int = 10

@description('Optional developer IP address that can be granted direct Azure SQL access.')
param developerIpAddress string = ''

@description('Azure OpenAI deployment name expected by the backend settings.')
param azureOpenAIDeploymentName string = 'gpt4o-deployment'

@description('Azure OpenAI API version used by the backend settings.')
param azureOpenAIApiVersion string = '2024-10-21'

@minValue(7)
@maxValue(730)
@description('Retention, in days, for the shared Log Analytics workspace.')
param logAnalyticsRetentionInDays int = 30

@allowed([
  'FC1'
])
@description('App Service plan SKU name used for the Flex Consumption Function App.')
param appServicePlanSkuName string = 'FC1'

@allowed([
  'FlexConsumption'
])
@description('App Service plan SKU tier used for the Flex Consumption Function App.')
param appServicePlanSkuTier string = 'FlexConsumption'

@description('App Service plan SKU name used for the private live admin site.')
param privateLiveAppServicePlanSkuName string = 'B1'

@description('App Service plan SKU tier used for the private live admin site.')
param privateLiveAppServicePlanSkuTier string = 'Basic'

var normalizedEnvironment = toLower(environment)
var suffix = substring(uniqueString(resourceGroup().id, environment), 0, 6)
var useExistingDocumentIntelligence = !empty(existingDocumentIntelligenceAccountName)
var useExistingOpenAI = !empty(existingOpenAIAccountName)
var storageAccountName = 'stdoc${normalizedEnvironment}${suffix}'
var serviceBusName = 'sb-doc-${normalizedEnvironment}-${suffix}'
var functionAppName = 'func-doc-${normalizedEnvironment}-${suffix}'
var publicSimulationStorageAccountName = 'stsim${normalizedEnvironment}${suffix}'
var publicFrontDoorProfileName = 'afd-doc-${normalizedEnvironment}-${suffix}'
var publicFrontDoorEndpointName = 'public-sim'
var publicFrontDoorOriginGroupName = 'public-sim-origin-group'
var publicFrontDoorOriginName = 'public-sim-origin'
var publicFrontDoorRouteName = 'public-sim-route'
var publicFrontDoorCustomDomainName = 'public-sim-domain'
var appServicePlanName = 'asp-doc-${normalizedEnvironment}-${suffix}'
var privateLiveAppServicePlanName = 'asp-live-${normalizedEnvironment}-${suffix}'
var privateLiveSiteName = 'admin-doc-${normalizedEnvironment}-${suffix}'
var privateLiveStartupCommand = 'bash -lc "set -e; APP_ROOT=/tmp/docintel-live; rm -rf \\$APP_ROOT; mkdir -p \\$APP_ROOT; tar --use-compress-program=unzstd -xf /home/site/wwwroot/output.tar.zst -C \\$APP_ROOT; cd \\$APP_ROOT; export PYTHONPATH=\\$APP_ROOT/src:\\$APP_ROOT/antenv/lib/python3.14/site-packages; exec python -m gunicorn --bind 0.0.0.0:$PORT --timeout 600 --access-logfile - --error-logfile - live_site_wsgi:app"'
var logAnalyticsName = 'log-doc-${normalizedEnvironment}-${suffix}'
var appInsightsName = 'appi-doc-${normalizedEnvironment}-${suffix}'
var keyVaultName = 'kv-doc-${normalizedEnvironment}-${suffix}'
var cosmosAccountName = 'cosdoc${normalizedEnvironment}${suffix}'
var sqlServerName = 'sql-doc-${normalizedEnvironment}-${suffix}'
var documentIntelligenceName = 'di-doc-${normalizedEnvironment}-${suffix}'
var openAIAccountName = 'aoai-doc-${normalizedEnvironment}-${suffix}'
var storageConnectionString = 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};EndpointSuffix=${az.environment().suffixes.storage};AccountKey=${storageAccount.listKeys().keys[0].value}'
var shouldDeployPublicFrontDoor = deployPublicSimulationSite && deployPublicFrontDoor
var shouldCreatePublicSimulationCustomDomain = shouldDeployPublicFrontDoor && !empty(publicSimulationCustomDomainName)
var shouldAssociatePublicSimulationCustomDomain = shouldCreatePublicSimulationCustomDomain && associatePublicSimulationCustomDomain
var shouldCreatePrivateLiveCustomDomain = deployPrivateLiveSite && !empty(privateLiveCustomDomainName)
var tags = {
  Environment: environment
  ManagedBy: 'Bicep'
  Project: 'Hybrid-Document-Intelligence-Platform'
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logAnalyticsName
  location: location
  tags: tags
  properties: {
    retentionInDays: logAnalyticsRetentionInDays
    sku: {
      name: 'PerGB2018'
    }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2024-01-01' = {
  name: storageAccountName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: normalizedEnvironment == 'prod' ? 'Standard_GRS' : 'Standard_LRS'
  }
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true
    isHnsEnabled: true
    isLocalUserEnabled: enableStorageSftp
    isSftpEnabled: enableStorageSftp
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Enabled'
    supportsHttpsTrafficOnly: true
  }
}

resource publicSimulationStorageAccount 'Microsoft.Storage/storageAccounts@2024-01-01' = if (deployPublicSimulationSite) {
  name: publicSimulationStorageAccountName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Enabled'
    supportsHttpsTrafficOnly: true
  }
}

resource publicFrontDoorProfile 'Microsoft.Cdn/profiles@2024-09-01' = if (shouldDeployPublicFrontDoor) {
  name: publicFrontDoorProfileName
  location: 'global'
  sku: {
    name: 'Standard_AzureFrontDoor'
  }
  tags: tags
  properties: {
    originResponseTimeoutSeconds: 60
  }
}

resource publicFrontDoorEndpoint 'Microsoft.Cdn/profiles/afdEndpoints@2024-09-01' = if (shouldDeployPublicFrontDoor) {
  parent: publicFrontDoorProfile
  location: 'global'
  name: publicFrontDoorEndpointName
  properties: {
    enabledState: 'Enabled'
  }
}

resource publicFrontDoorOriginGroup 'Microsoft.Cdn/profiles/originGroups@2024-09-01' = if (shouldDeployPublicFrontDoor) {
  parent: publicFrontDoorProfile
  name: publicFrontDoorOriginGroupName
  properties: {
    healthProbeSettings: {
      probeIntervalInSeconds: 120
      probePath: '/'
      probeProtocol: 'Https'
      probeRequestType: 'GET'
    }
    loadBalancingSettings: {
      additionalLatencyInMilliseconds: 50
      sampleSize: 4
      successfulSamplesRequired: 3
    }
    sessionAffinityState: 'Disabled'
  }
}

var publicSimulationWebEndpoint = deployPublicSimulationSite ? publicSimulationStorageAccount!.properties.primaryEndpoints.web : ''
var publicSimulationWebHostName = !empty(publicSimulationWebEndpoint)
  ? split(replace(publicSimulationWebEndpoint, 'https://', ''), '/')[0]
  : ''

resource publicFrontDoorOrigin 'Microsoft.Cdn/profiles/originGroups/origins@2024-09-01' = if (shouldDeployPublicFrontDoor) {
  parent: publicFrontDoorOriginGroup
  name: publicFrontDoorOriginName
  properties: {
    enabledState: 'Enabled'
    enforceCertificateNameCheck: true
    hostName: publicSimulationWebHostName
    httpsPort: 443
    originHostHeader: publicSimulationWebHostName
    priority: 1
    weight: 1000
  }
}

resource publicFrontDoorCustomDomain 'Microsoft.Cdn/profiles/customDomains@2024-09-01' = if (shouldCreatePublicSimulationCustomDomain) {
  parent: publicFrontDoorProfile
  name: publicFrontDoorCustomDomainName
  properties: {
    hostName: publicSimulationCustomDomainName
    tlsSettings: {
      certificateType: 'ManagedCertificate'
      minimumTlsVersion: 'TLS12'
    }
  }
}

resource publicFrontDoorRoute 'Microsoft.Cdn/profiles/afdEndpoints/routes@2024-09-01' = if (shouldDeployPublicFrontDoor) {
  parent: publicFrontDoorEndpoint
  name: publicFrontDoorRouteName
  properties: {
    customDomains: shouldAssociatePublicSimulationCustomDomain
      ? [
          {
            id: publicFrontDoorCustomDomain.id
          }
        ]
      : []
    enabledState: 'Enabled'
    forwardingProtocol: 'HttpsOnly'
    httpsRedirect: 'Enabled'
    linkToDefaultDomain: 'Enabled'
    originGroup: {
      id: publicFrontDoorOriginGroup.id
    }
    patternsToMatch: [
      '/*'
    ]
    supportedProtocols: [
      'Http'
      'Https'
    ]
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2024-01-01' = {
  parent: storageAccount
  name: 'default'
}

resource rawContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2024-01-01' = {
  parent: blobService
  name: containerNames.raw
  properties: {
    publicAccess: 'None'
  }
}

resource processedContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2024-01-01' = {
  parent: blobService
  name: containerNames.processed
  properties: {
    publicAccess: 'None'
  }
}

resource quarantineContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2024-01-01' = {
  parent: blobService
  name: containerNames.quarantine
  properties: {
    publicAccess: 'None'
  }
}

resource functionDeploymentContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2024-01-01' = {
  parent: blobService
  name: functionDeploymentContainerName
  properties: {
    publicAccess: 'None'
  }
}

resource storageLifecyclePolicy 'Microsoft.Storage/storageAccounts/managementPolicies@2024-01-01' = if (enableBlobLifecyclePolicy) {
  parent: storageAccount
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'deleteRawLandingBlobs'
          enabled: true
          type: 'Lifecycle'
          definition: {
            actions: {
              baseBlob: {
                delete: {
                  daysAfterModificationGreaterThan: blobLifecycleRetentionDays.raw
                }
              }
            }
            filters: {
              blobTypes: [
                'blockBlob'
              ]
              prefixMatch: [
                '${containerNames.raw}/'
              ]
            }
          }
        }
        {
          name: 'deleteProcessedLandingBlobs'
          enabled: true
          type: 'Lifecycle'
          definition: {
            actions: {
              baseBlob: {
                delete: {
                  daysAfterModificationGreaterThan: blobLifecycleRetentionDays.processed
                }
              }
            }
            filters: {
              blobTypes: [
                'blockBlob'
              ]
              prefixMatch: [
                '${containerNames.processed}/'
              ]
            }
          }
        }
        {
          name: 'deleteQuarantineLandingBlobs'
          enabled: true
          type: 'Lifecycle'
          definition: {
            actions: {
              baseBlob: {
                delete: {
                  daysAfterModificationGreaterThan: blobLifecycleRetentionDays.quarantine
                }
              }
            }
            filters: {
              blobTypes: [
                'blockBlob'
              ]
              prefixMatch: [
                '${containerNames.quarantine}/'
              ]
            }
          }
        }
        {
          name: 'deleteFunctionReleaseBlobs'
          enabled: true
          type: 'Lifecycle'
          definition: {
            actions: {
              baseBlob: {
                delete: {
                  daysAfterModificationGreaterThan: blobLifecycleRetentionDays.functionReleases
                }
              }
            }
            filters: {
              blobTypes: [
                'blockBlob'
              ]
              prefixMatch: [
                '${functionDeploymentContainerName}/'
              ]
            }
          }
        }
      ]
    }
  }
}

resource serviceBusNamespace 'Microsoft.ServiceBus/namespaces@2024-01-01' = if (deployServiceBus) {
  name: serviceBusName
  location: location
  tags: tags
  sku: {
    name: 'Standard'
    tier: 'Standard'
  }
  properties: {
    disableLocalAuth: false
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
    zoneRedundant: false
  }
}

resource ingestionQueue 'Microsoft.ServiceBus/namespaces/queues@2024-01-01' = if (deployServiceBus) {
  parent: serviceBusNamespace
  name: queueNames.ingestion
}

resource reviewQueue 'Microsoft.ServiceBus/namespaces/queues@2024-01-01' = if (deployServiceBus) {
  parent: serviceBusNamespace
  name: queueNames.review
}

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = if (deployCosmos) {
  name: cosmosAccountName
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    databaseAccountOfferType: 'Standard'
    disableKeyBasedMetadataWriteAccess: false
    enableAutomaticFailover: false
    locations: [
      {
        failoverPriority: 0
        isZoneRedundant: false
        locationName: location
      }
    ]
    publicNetworkAccess: 'Enabled'
    capabilities: [
      {
        name: 'EnableServerless'
      }
    ]
  }
}

resource cosmosSqlDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = if (deployCosmos) {
  parent: cosmosAccount
  name: cosmosDatabaseName
  properties: {
    resource: {
      id: cosmosDatabaseName
    }
  }
}

resource cosmosReviewContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = if (deployCosmos) {
  parent: cosmosSqlDatabase
  name: cosmosReviewContainerName
  properties: {
    resource: {
      id: cosmosReviewContainerName
      indexingPolicy: {
        automatic: true
        indexingMode: 'consistent'
        includedPaths: [
          {
            path: '/*'
          }
        ]
        excludedPaths: [
          {
            path: '/"_etag"/?'
          }
        ]
      }
      partitionKey: {
        kind: 'Hash'
        paths: [
          '/status'
        ]
        version: 2
      }
    }
  }
}

resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' = if (deploySql) {
  name: sqlServerName
  location: location
  tags: tags
  properties: {
    administratorLogin: sqlAdministratorLogin
    administratorLoginPassword: sqlAdministratorPassword
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
  }
}

resource sqlAllowAzureServices 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = if (deploySql) {
  parent: sqlServer
  name: 'AllowAzureServices'
  properties: {
    endIpAddress: '0.0.0.0'
    startIpAddress: '0.0.0.0'
  }
}

resource sqlDeveloperFirewallRule 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = if (deploySql && !empty(developerIpAddress)) {
  parent: sqlServer
  name: 'AllowDeveloperIp'
  properties: {
    endIpAddress: developerIpAddress
    startIpAddress: developerIpAddress
  }
}

resource sqlDatabase 'Microsoft.Sql/servers/databases@2023-08-01-preview' = if (deploySql) {
  parent: sqlServer
  name: sqlDatabaseName
  location: location
  sku: {
    name: 'Basic'
    tier: 'Basic'
  }
  properties: {
    collation: 'SQL_Latin1_General_CP1_CI_AS'
  }
}

resource documentIntelligenceAccount 'Microsoft.CognitiveServices/accounts@2023-05-01' = if (deployAiServices) {
  name: documentIntelligenceName
  location: documentIntelligenceLocation
  tags: tags
  kind: 'FormRecognizer'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: documentIntelligenceName
    publicNetworkAccess: 'Enabled'
  }
}

resource existingDocumentIntelligenceAccount 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = if (useExistingDocumentIntelligence) {
  name: existingDocumentIntelligenceAccountName
}

resource openAIAccount 'Microsoft.CognitiveServices/accounts@2023-05-01' = if (deployAiServices) {
  name: openAIAccountName
  location: openAILocation
  tags: tags
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: openAIAccountName
    publicNetworkAccess: 'Enabled'
  }
}

resource existingOpenAIAccount 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = if (useExistingOpenAI) {
  name: existingOpenAIAccountName
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: tags
  properties: {
    enableRbacAuthorization: true
    enableSoftDelete: true
    enabledForDeployment: false
    enabledForDiskEncryption: false
    enabledForTemplateDeployment: false
    publicNetworkAccess: 'Enabled'
    sku: {
      family: 'A'
      name: 'standard'
    }
    softDeleteRetentionInDays: 90
    tenantId: tenant().tenantId
  }
}

var cosmosEndpoint = deployCosmos ? cosmosAccount!.properties.documentEndpoint : ''
var cosmosPrimaryKey = deployCosmos ? cosmosAccount!.listKeys().primaryMasterKey : ''
var documentIntelligenceEndpoint = useExistingDocumentIntelligence
  ? existingDocumentIntelligenceAccount!.properties.endpoint
  : (deployAiServices ? documentIntelligenceAccount!.properties.endpoint : '')
var documentIntelligenceKey = useExistingDocumentIntelligence
  ? existingDocumentIntelligenceAccount!.listKeys().key1
  : (deployAiServices ? documentIntelligenceAccount!.listKeys().key1 : '')
var openAIApiKey = useExistingOpenAI
  ? existingOpenAIAccount!.listKeys().key1
  : (deployAiServices ? openAIAccount!.listKeys().key1 : '')
var openAIEndpoint = useExistingOpenAI
  ? existingOpenAIAccount!.properties.endpoint
  : (deployAiServices ? openAIAccount!.properties.endpoint : '')
var serviceBusRootRuleResourceId = resourceId('Microsoft.ServiceBus/namespaces/authorizationRules', serviceBusName, 'RootManageSharedAccessKey')
var serviceBusConnectionString = deployServiceBus ? listKeys(serviceBusRootRuleResourceId, '2024-01-01').primaryConnectionString : ''
var sqlConnectionString = deploySql ? 'Server=tcp:${sqlServer.name}${az.environment().suffixes.sqlServerHostname},1433;Initial Catalog=${sqlDatabase.name};Persist Security Info=False;User ID=${sqlAdministratorLogin};Password=${sqlAdministratorPassword};MultipleActiveResultSets=False;Encrypt=True;TrustServerCertificate=False;Connection Timeout=30;' : ''

resource appServicePlan 'Microsoft.Web/serverfarms@2024-04-01' = if (deployFunctionApp) {
  name: appServicePlanName
  location: location
  kind: 'functionapp'
  tags: tags
  sku: {
    name: appServicePlanSkuName
    tier: appServicePlanSkuTier
  }
  properties: {
    reserved: true
  }
}

resource privateLiveAppServicePlan 'Microsoft.Web/serverfarms@2023-12-01' = if (deployPrivateLiveSite) {
  name: privateLiveAppServicePlanName
  location: privateLiveLocation
  tags: tags
  sku: {
    name: privateLiveAppServicePlanSkuName
    tier: privateLiveAppServicePlanSkuTier
  }
  properties: {
    reserved: true
  }
}

resource functionApp 'Microsoft.Web/sites@2024-04-01' = if (deployFunctionApp) {
  name: functionAppName
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    httpsOnly: true
    serverFarmId: appServicePlan.id
    siteConfig: {
      ftpsState: 'Disabled'
      http20Enabled: true
      appSettings: [
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
        {
          name: 'AzureWebJobsStorage'
          value: storageConnectionString
        }
        {
          name: 'DOCINT_DEPLOYMENT_STORAGE_CONNECTION_STRING'
          value: storageConnectionString
        }
        {
          name: 'AzureWebJobsFeatureFlags'
          value: 'EnableWorkerIndexing'
        }
        {
          name: 'DOCINT_AZURE_OPENAI_API_KEY'
          value: openAIApiKey
        }
        {
          name: 'DOCINT_AZURE_OPENAI_API_VERSION'
          value: azureOpenAIApiVersion
        }
        {
          name: 'DOCINT_AZURE_OPENAI_DEPLOYMENT'
          value: azureOpenAIDeploymentName
        }
        {
          name: 'DOCINT_AZURE_OPENAI_ENDPOINT'
          value: openAIEndpoint
        }
        {
          name: 'DOCINT_COSMOS_DATABASE_NAME'
          value: cosmosDatabaseName
        }
        {
          name: 'DOCINT_COSMOS_ENDPOINT'
          value: cosmosEndpoint
        }
        {
          name: 'DOCINT_COSMOS_KEY'
          value: cosmosPrimaryKey
        }
        {
          name: 'DOCINT_COSMOS_REVIEW_CONTAINER_NAME'
          value: cosmosReviewContainerName
        }
        {
          name: 'DOCINT_DOCUMENT_INTELLIGENCE_ENDPOINT'
          value: documentIntelligenceEndpoint
        }
        {
          name: 'DOCINT_DOCUMENT_INTELLIGENCE_KEY'
          value: documentIntelligenceKey
        }
        {
          name: 'DOCINT_DOCUMENT_INTELLIGENCE_MODEL_ID'
          value: 'prebuilt-layout'
        }
        {
          name: 'DOCINT_ENABLE_DURABLE_WORKFLOWS'
          value: 'false'
        }
        {
          name: 'DOCINT_ENVIRONMENT_NAME'
          value: environment
        }
        {
          name: 'DOCINT_INGESTION_QUEUE_NAME'
          value: deployServiceBus ? queueNames.ingestion : ''
        }
        {
          name: 'DOCINT_LOW_CONFIDENCE_THRESHOLD'
          value: '0.80'
        }
        {
          name: 'DOCINT_PROCESSED_CONTAINER_NAME'
          value: containerNames.processed
        }
        {
          name: 'DOCINT_QUARANTINE_CONTAINER_NAME'
          value: containerNames.quarantine
        }
        {
          name: 'DOCINT_RAW_CONTAINER_NAME'
          value: containerNames.raw
        }
        {
          name: 'DOCINT_REQUIRED_FIELDS'
          value: 'account_number,statement_date'
        }
        {
          name: 'DOCINT_REVIEW_APP_ORIGIN'
          value: 'http://localhost:5173'
        }
        {
          name: 'DOCINT_REVIEW_QUEUE_NAME'
          value: deployServiceBus ? queueNames.review : ''
        }
        {
          name: 'DOCINT_REVIEW_API_DEFAULT_LIMIT'
          value: '25'
        }
        {
          name: 'DOCINT_SERVICE_BUS_CONNECTION_STRING'
          value: serviceBusConnectionString
        }
        {
          name: 'DOCINT_SQL_ACCOUNT_TABLE_NAME'
          value: sqlAccountTableName
        }
        {
          name: 'DOCINT_SQL_CONNECTION_STRING'
          value: sqlConnectionString
        }
        {
          name: 'DOCINT_SQL_LOOKUP_TOP_N'
          value: string(sqlLookupTopN)
        }
        {
          name: 'DOCINT_STORAGE_CONNECTION_STRING'
          value: storageConnectionString
        }
        {
          name: 'PYTHONPATH'
          value: '/home/site/wwwroot/src'
        }
      ]
      minTlsVersion: '1.2'
    }
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storageAccount.properties.primaryEndpoints.blob}${functionDeploymentContainerName}'
          authentication: {
            type: 'StorageAccountConnectionString'
            storageAccountConnectionStringName: 'DOCINT_DEPLOYMENT_STORAGE_CONNECTION_STRING'
          }
        }
      }
      runtime: {
        name: 'python'
        version: '3.14'
      }
      scaleAndConcurrency: {
        instanceMemoryMB: functionInstanceMemoryMB
        maximumInstanceCount: functionMaximumInstanceCount
      }
    }
  }
}

resource privateLiveSite 'Microsoft.Web/sites@2023-12-01' = if (deployPrivateLiveSite) {
  name: privateLiveSiteName
  location: privateLiveLocation
  tags: tags
  kind: 'app,linux'
  properties: {
    httpsOnly: true
    publicNetworkAccess: 'Enabled'
    reserved: true
    serverFarmId: privateLiveAppServicePlan.id
    siteConfig: {
      alwaysOn: true
      appCommandLine: privateLiveStartupCommand
      appSettings: [
        {
          name: 'ENABLE_ORYX_BUILD'
          value: 'true'
        }
        {
          name: 'PYTHONPATH'
          value: '/home/site/wwwroot/src'
        }
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
      ]
      ftpsState: 'Disabled'
      http20Enabled: true
      linuxFxVersion: 'PYTHON|3.14'
      minTlsVersion: '1.2'
      pythonVersion: '3.14'
    }
  }
}

output appInsightsConnectionString string = appInsights.properties.ConnectionString
output cosmosAccountName string = deployCosmos ? cosmosAccount.name : ''
output cosmosEndpoint string = cosmosEndpoint
output documentIntelligenceAccountName string = useExistingDocumentIntelligence ? existingDocumentIntelligenceAccount.name : (deployAiServices ? documentIntelligenceAccount.name : '')
output documentIntelligenceEndpoint string = documentIntelligenceEndpoint
output functionAppName string = functionAppName
output functionAppHostname string = deployFunctionApp ? functionApp!.properties.defaultHostName : ''
output functionDeploymentContainerName string = functionDeploymentContainer.name
output keyVaultName string = keyVault.name
output openAIAccountName string = useExistingOpenAI ? existingOpenAIAccount.name : (deployAiServices ? openAIAccount.name : '')
output openAIEndpoint string = openAIEndpoint
output publicFrontDoorEndpointHostname string = shouldDeployPublicFrontDoor ? publicFrontDoorEndpoint!.properties.hostName : ''
output publicFrontDoorEndpointUrl string = shouldDeployPublicFrontDoor ? 'https://${publicFrontDoorEndpoint!.properties.hostName}' : ''
output publicFrontDoorProfileName string = shouldDeployPublicFrontDoor ? publicFrontDoorProfile.name : ''
output publicSimulationCustomDomainAssociationRequested bool = shouldAssociatePublicSimulationCustomDomain
output publicSimulationCustomDomainDnsTarget string = shouldDeployPublicFrontDoor ? publicFrontDoorEndpoint!.properties.hostName : ''
output publicSimulationCustomDomainHostName string = shouldCreatePublicSimulationCustomDomain ? publicFrontDoorCustomDomain!.properties.hostName : ''
output publicSimulationCustomDomainValidationRecordName string = shouldCreatePublicSimulationCustomDomain ? '_dnsauth.${publicSimulationCustomDomainName}' : ''
output publicSimulationCustomDomainValidationState string = shouldCreatePublicSimulationCustomDomain ? publicFrontDoorCustomDomain!.properties.domainValidationState : ''
output publicSimulationCustomDomainValidationToken string = shouldCreatePublicSimulationCustomDomain ? publicFrontDoorCustomDomain!.properties.validationProperties.validationToken : ''
output publicSimulationStorageAccountName string = deployPublicSimulationSite ? publicSimulationStorageAccount.name : ''
output privateLiveSiteCustomDomainDnsTarget string = deployPrivateLiveSite ? privateLiveSite!.properties.defaultHostName : ''
output privateLiveSiteCustomDomainHostName string = shouldCreatePrivateLiveCustomDomain ? privateLiveCustomDomainName : ''
output privateLiveSiteCustomDomainValidationRecordName string = shouldCreatePrivateLiveCustomDomain ? 'asuid.${privateLiveCustomDomainName}' : ''
output privateLiveSiteCustomDomainValidationToken string = deployPrivateLiveSite ? privateLiveSite!.properties.customDomainVerificationId : ''
output privateLiveSiteHostname string = deployPrivateLiveSite ? privateLiveSite!.properties.defaultHostName : ''
output privateLiveSiteName string = deployPrivateLiveSite ? privateLiveSite.name : ''
output privateLiveSiteUrl string = deployPrivateLiveSite ? 'https://${privateLiveSite!.properties.defaultHostName}' : ''
output rawContainerName string = containerNames.raw
output reviewQueueName string = deployServiceBus ? reviewQueue.name : ''
output serviceBusNamespace string = deployServiceBus ? serviceBusNamespace.name : ''
output sqlDatabaseName string = deploySql ? sqlDatabase.name : ''
output sqlServerName string = deploySql ? sqlServer.name : ''
output storageAccountName string = storageAccount.name
output storageAccountBlobEndpoint string = storageAccount.properties.primaryEndpoints.blob
