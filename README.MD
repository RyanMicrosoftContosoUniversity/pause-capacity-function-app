# Fabric Automation Framework
Note that this project is for POC purposes only.  Please see DISCLAIMER.md for more details


This Sample Code is provided for the purpose of illustration only and is not intended to be used in a production environment.
THIS SAMPLE CODE AND ANY RELATED INFORMATION ARE PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, 
EITHER EXPRESSED OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE IMPLIED WARRANTIES OF MERCHANTABILITY 
AND/OR FITNESS FOR A PARTICULAR PURPOSE.  We grant You a nonexclusive, royalty-free right to use and 
modify the Sample Code and to reproduce and distribute the object code form of the Sample Code, provided that 
You agree: (i) to not use Our name, logo, or trademarks to market Your software product in which the Sample Code
is embedded; (ii) to include a valid copyright notice on Your software product in which the Sample Code is embedded;
and (iii) to indemnify, hold harmless, and defend Us and Our suppliers from and against any claims or lawsuits, 
including attorneys’ fees, that arise or result from the use or distribution of the Sample Code.



A function app for pausing fabric capacities

## Table of Contents

- [Introduction](#introduction)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Contributing](#contributing)
- [License](#license)

## Introduction

This is a function app aimed at setting a function app at a certain time to trigger and pausing all capacities in that resource group to reduce spend

## Features


## Installation

Follow the steps at this other github page: https://github.com/RyanMicrosoftContosoUniversity/fabric-utils to ensure all dependencies are in place


Creation of a new function app via VS Code (note, this can be created and updated in the Azure Portal as well)

![Alt text](docs\Capacity_App\requirements-txt-file.png)


Ensure that the Azure extension is installed from the VS Code Marketplace

To create a new function app, first navigate to the command pallette

![Alt text](docs\Capacity_App\command-palette.png)


Create a new project for Azure Functions
![Alt text](docs\Capacity_App\create-new-project.png)


Add code to function app
![Alt text](docs\Capacity_App\timer-trigger-code.png)

Use a similar flow with the command pallette to publish app to Azure

Add Environment Variables for the app
![Alt text](docs\Capacity_App\environment-variables.png)

![Alt text](docs\Capacity_App\add-environment-variables.png)


Test the app
![Alt text](docs\Capacity_App\test-app.png)











Access the POC Code:

    1. Navigate to fabric-automation-framework - Repos (azure.com)
    2. Clone the code in local git

![Alt text](docs\images\POC_11.png)

    3. Pip install the poc code:

![Alt text](docs\images\POC_12.png)

    4. Adjust the configuration file: docs\non-prod-spn-config.json to reflect your resources

![Alt text](docs\images\POC_12.png)


To test locally, run the script at: scripts\metadata_scan.py to write the scan files to the local docs folder:

![Alt text](docs\images\POC_13.png)



To perform ETL on the scan result, see the ipynb file here: scripts\process_metadata_scan.ipynb
