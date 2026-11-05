# Network troubleshooting playbook

Lumenvale Home Systems support handbook. All products and policies are fictional.

Local control and stored schedules continue during an internet outage if the home network and bridge remain available. Remote commands are unavailable.

The controller app discovers devices through mDNS. Guest isolation can block discovery even with a strong Wi-Fi signal.

A bridge with no DHCP lease shows an amber double blink. Check the cable and DHCP service before attempting any reset.

DNS failures can prevent remote status updates while LAN commands still work. A successful LAN command does not prove that DNS is working.
