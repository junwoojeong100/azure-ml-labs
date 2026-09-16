param location string = resourceGroup().location
param storageAccountName string
param workspaceName string
param managedIdentityName string = 'id-aml-mlops-compute'
param sshPublicKey string
param vnetName string = 'vnet-aml-mlops'
param runnerName string = 'vm-aml-lab-runner'
param adminUsername string = 'azureuser'

resource storage 'Microsoft.Storage/storageAccounts@2024-01-01' existing = {
  name: storageAccountName
}

resource workspace 'Microsoft.MachineLearningServices/workspaces@2024-04-01' existing = {
  name: workspaceName
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: managedIdentityName
}

resource runnerNsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: '${runnerName}-nsg'
  location: location
  properties: {
    securityRules: [
      {
        name: 'DenyAllInbound'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: ['10.73.0.0/16']
    }
    subnets: [
      {
        name: 'runner'
        properties: {
          addressPrefix: '10.73.1.0/24'
          defaultOutboundAccess: true
          networkSecurityGroup: {
            id: runnerNsg.id
          }
        }
      }
      {
        name: 'private-endpoints'
        properties: {
          addressPrefix: '10.73.2.0/24'
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

var services = ['blob', 'file']

resource zones 'Microsoft.Network/privateDnsZones@2020-06-01' = [for service in services: {
  name: 'privatelink.${service}.core.windows.net'
  location: 'global'
}]

resource links 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = [for (service, index) in services: {
  parent: zones[index]
  name: '${vnetName}-${service}'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}]

resource privateEndpoints 'Microsoft.Network/privateEndpoints@2023-11-01' = [for service in services: {
  name: 'pe-aml-${service}'
  location: location
  properties: {
    subnet: {
      id: '${vnet.id}/subnets/private-endpoints'
    }
    privateLinkServiceConnections: [
      {
        name: 'aml-${service}'
        properties: {
          privateLinkServiceId: storage.id
          groupIds: [service]
        }
      }
    ]
  }
}]

resource zoneGroups 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = [for (service, index) in services: {
  parent: privateEndpoints[index]
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: service
        properties: {
          privateDnsZoneId: zones[index].id
        }
      }
    ]
  }
}]

var workspaceDnsNames = ['privatelink.api.azureml.ms', 'privatelink.notebooks.azure.net']

resource workspaceZones 'Microsoft.Network/privateDnsZones@2020-06-01' = [for zone in workspaceDnsNames: {
  name: zone
  location: 'global'
}]

resource workspaceLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = [for (zone, index) in workspaceDnsNames: {
  parent: workspaceZones[index]
  name: '${vnetName}-workspace'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}]

resource workspaceEndpoint 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: 'pe-aml-workspace'
  location: location
  properties: {
    subnet: {
      id: '${vnet.id}/subnets/private-endpoints'
    }
    privateLinkServiceConnections: [
      {
        name: 'aml-workspace'
        properties: {
          privateLinkServiceId: workspace.id
          groupIds: ['amlworkspace']
        }
      }
    ]
  }
}

resource workspaceZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: workspaceEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [for (zone, index) in workspaceDnsNames: {
      name: 'workspace-${index}'
      properties: {
        privateDnsZoneId: workspaceZones[index].id
      }
    }]
  }
}

resource nic 'Microsoft.Network/networkInterfaces@2023-11-01' = {
  name: '${runnerName}-nic'
  location: location
  properties: {
    ipConfigurations: [
      {
        name: 'primary'
        properties: {
          privateIPAllocationMethod: 'Dynamic'
          subnet: {
            id: '${vnet.id}/subnets/runner'
          }
        }
      }
    ]
  }
}

resource runner 'Microsoft.Compute/virtualMachines@2024-03-01' = {
  name: runnerName
  location: location
  tags: {
    purpose: 'aml-mlops-hands-on'
    lifecycle: 'temporary-private-orchestrator'
  }
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    hardwareProfile: {
      vmSize: 'Standard_D2s_v3'
    }
    osProfile: {
      computerName: runnerName
      adminUsername: adminUsername
      linuxConfiguration: {
        disablePasswordAuthentication: true
        ssh: {
          publicKeys: [
            {
              path: '/home/${adminUsername}/.ssh/authorized_keys'
              keyData: sshPublicKey
            }
          ]
        }
      }
    }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: '0001-com-ubuntu-server-jammy'
        sku: '22_04-lts-gen2'
        version: 'latest'
      }
      osDisk: {
        name: '${runnerName}-os'
        createOption: 'FromImage'
        deleteOption: 'Delete'
        managedDisk: {
          storageAccountType: 'Standard_LRS'
        }
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: nic.id
          properties: {
            deleteOption: 'Delete'
          }
        }
      ]
    }
  }
}

output runnerSubnetId string = '${vnet.id}/subnets/runner'
output runnerVmName string = runner.name
output managedIdentityClientId string = identity.properties.clientId
