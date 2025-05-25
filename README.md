This project is work in progress and just got started

The relay guardian is a PC/Linux/Mac application which allow configuring and troubleshooting the Modbus relay project.

Core function:
 * Built-in Modbus support - acts as the bus master
 * Recovery of the relay module
 * Reconfiguration of the relay
 * Extract statistics from the relay
 * Visual infeed voltage
 * Run a diagnostic of the module

## Implementation

The application is written in Python (why not!) using the Pivy UI framework and PivyMD widgets.
It also used pymodbus for the modbus RTU part.

## Build and installation

The aim is to package it for Windows and Linux. A docker may be added to manage the build.
