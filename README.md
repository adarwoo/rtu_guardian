This project is work in progress and is now getting there...

The RTU guardian is a PC/Linux/Mac application which allow configuring and troubleshooting Modbus RTU devices, with some devices being fully managed - in this case - all my Modbus devices.

Core function:
 * Built-in Modbus support - acts as the bus master
 * Bus scanning
 * Adding devices of different types
 * Dynamic device type discovery
 * Recovery mode for device supporting it
 * Full support of the ARex Relay - covering 100% of the modbus ICD

## Implementation

The application is written in Python (why not!) using the Textrual TUI framework.
It also uses pymodbus for the modbus RTU part.

## Build and installation

The Poetry package manager is used for integrated development in Windows/Linux/Mac.

<<<<<<< HEAD
## Screenshot

=======
![RTUGuardian_2025-09-16T01_25_51_811069](https://github.com/user-attachments/assets/d6b2887d-67a2-4439-a37b-ed4e814aa633)
