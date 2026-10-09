# Real Indian telephone connectivity

Akki currently manages private Asterisk SIP-to-SIP calls to test extension **1001**. Existing private call/AudioSocket checks use fictional consenting participants. There is no public telephone-network route, trunk, carrier account or number activated. The owner confirmed no provider has been obtained.

Asterisk software cannot itself connect ordinary Indian mobile/landline numbers for free. Before a live connector can be implemented and tested against an actual carrier, obtain an eligible licensed provider arrangement and its exact technical specification:

1. Written eligibility for the intended AI-assisted business outreach, required consent/telecom registrations and permitted caller identification.
2. SIP/PBX connection method, provider host/region, authentication or IP allowlisting, supported codecs, encryption, RTP ranges and NAT guidance. Some providers offer only API calling rather than a generic SIP trunk.
3. Verified consenting test recipients, approved calling windows and test purpose; no general unsolicited dialing.
4. Explicit approved rates, a prepaid or otherwise hard carrier spending limit where available, low call quotas and a way to disable calling immediately.
5. Recording/transcription permissions, storage location/retention requirements and provider acceptable-use rules.

Keep credentials out of chat, source code and issue reports. No trial is represented as permanently free. Merely setting an environment flag will not enable PSTN: the current dial command remains the fixed private endpoint, and external-destination rejection tests must continue passing.

After a provider is selected, implement its adapter, validate signed callbacks or SIP authentication, test its error/status handling, cancellation, opt-out, quota enforcement and two-way audio with consenting numbers. Verify actual charges in the provider account. That carrier-specific integration and commercial authorization cannot be verified without the account, routing details and approval; a generic untested trunk template would not establish working telephone connectivity.
