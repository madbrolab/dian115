#!/usr/bin/env node
// Read-only malware audit. It never runs the plugin it inspects.
import { cli } from '../assets/public-kit/conformance/audit.mjs'

cli(process.argv.slice(2))
