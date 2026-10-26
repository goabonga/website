#!/usr/bin/env node
/**
 * Generate Jinja2 template from index.html
 *
 * This script converts the development index.html into a Jinja2 template
 * by replacing hardcoded values with template variables.
 *
 * Usage: node scripts/generate-template.js
 */

import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const rootDir = join(__dirname, '..');

const SOURCE = join(rootDir, 'dist', 'index.html');
const TARGET = join(rootDir, '..', 'src', 'frontend', 'templates', 'index.html');

// Mapping of hardcoded values to Jinja2 variables.
// Values placed in the JavaScript configuration go through the tojson filter: HTML escaping
// would leave entities such as &#39; in the strings the web client reads.
// ORDER MATTERS: More specific patterns must come before generic ones
const replacements = [
  // Legal info in JS config (must be before generic "GOABONGA" pattern)
  { pattern: /companyName: "GOABONGA"/g, replacement: 'companyName: {{ legal_company_name | tojson }}' },
  { pattern: /address: "Terre Rouge"/g, replacement: 'address: {{ legal_address | tojson }}' },
  { pattern: /city: "26410 Boulc"/g, replacement: 'city: {{ legal_city | tojson }}' },
  { pattern: /country: "FRANCE"/g, replacement: 'country: {{ legal_country | tojson }}' },
  { pattern: /directorName: "Chris Becker"/g, replacement: 'directorName: {{ legal_director_name | tojson }}' },
  { pattern: /hostName: "OVH"/g, replacement: 'hostName: {{ legal_host_name | tojson }}' },
  { pattern: /hostAddress: "140, Quai du Sartel"/g, replacement: 'hostAddress: {{ legal_host_address | tojson }}' },
  { pattern: /hostCity: "59100 ROUBAIX"/g, replacement: 'hostCity: {{ legal_host_city | tojson }}' },
  { pattern: /hostCountry: "France"/g, replacement: 'hostCountry: {{ legal_host_country | tojson }}' },
  { pattern: /hostPhone: "0899 701 761"/g, replacement: 'hostPhone: {{ legal_host_phone | tojson }}' },
  { pattern: /hostWebsite: "ovh.com"/g, replacement: 'hostWebsite: {{ legal_host_website | tojson }}' },

  // App config (appName: "GOABONGA" after companyName is handled)
  { pattern: /appName: "GOABONGA"/g, replacement: 'appName: {{ app_name | tojson }}' },
  { pattern: /GOABONGA - Developer Portfolio/g, replacement: '{{ app_name }} - Developer Portfolio' },
  { pattern: /<title>GOABONGA<\/title>/g, replacement: '<title>{{ app_name }}</title>' },
  { pattern: />GOABONGA</g, replacement: '>{{ app_name }}<' },

  // Auth, API, and Analytics URLs
  { pattern: /"https:\/\/auth\.goabonga\.com"/g, replacement: '{{ auth_url | tojson }}' },
  { pattern: /apiUrl: ""/g, replacement: 'apiUrl: {{ api_url | tojson }}' },
  { pattern: /analyticsUrl: "https:\/\/ua\.goabonga\.com"/g, replacement: 'analyticsUrl: {{ analytics_url | tojson }}' },

  // Client ID
  { pattern: /"ea2457629d5f4680e3968df232849fde"/g, replacement: '{{ client_id | tojson }}' },

  // Welcome section
  { pattern: /welcomeName: "Chris"/g, replacement: 'welcomeName: {{ welcome_name | tojson }}' },
  { pattern: /welcomeWords: \["super", "fucking", "french", "cool"\]/g, replacement: 'welcomeWords: {{ welcome_words | tojson }}.split(",")' },
  { pattern: /I'm Chris,/g, replacement: "I'm {{ welcome_name }}," },

  // Policies section - static text with app name
  { pattern: /The website goabonga\.com/g, replacement: 'The website {{ app_name | lower }}.com' },

  // Social links
  { pattern: /href="https:\/\/linkedin\.com\/in\/goabonga"/g, replacement: 'href="{{ social_linkedin }}"' },
  { pattern: /href="https:\/\/github\.com\/goabonga"/g, replacement: 'href="{{ social_github }}"' },
  { pattern: /href="https:\/\/huggingface\.co\/goabonga"/g, replacement: 'href="{{ social_huggingface }}"' },
];

// Post-processing replacements for the policies section HTML
// These run AFTER the main replacements to fix any incorrect substitutions
const policiesSectionReplacements = [
  // Fix: In policies HTML, company name should use legal_company_name, not app_name
  // The main replacement converts <b>GOABONGA</b> to <b>{{ app_name }}</b>
  // We need to fix it specifically in the policies section context
  { pattern: /<b>This website is published by:<\/b><br\/>\s*<b>\{\{ app_name \}\}<\/b>/g, replacement: '<b>This website is published by:</b><br/>\n              <b>{{ legal_company_name }}</b>' },

  // Address and location in policies
  { pattern: /Terre Rouge<br\/>/g, replacement: '{{ legal_address }}<br/>' },
  { pattern: /26410 Boulc FRANCE/g, replacement: '{{ legal_city }} {{ legal_country }}' },
  { pattern: /<b>Publication Director:<\/b> Chris Becker/g, replacement: '<b>Publication Director:</b> {{ legal_director_name }}' },

  // Host info in policies
  { pattern: /OVH<br\/>\s*140, Quai du Sartel<br\/>/g, replacement: '{{ legal_host_name }}<br/>\n              {{ legal_host_address }}<br/>' },
  { pattern: /59100 ROUBAIX France<br\/>/g, replacement: '{{ legal_host_city }} {{ legal_host_country }}<br/>' },
  { pattern: /Phone: 0899 701 761<br\/>/g, replacement: '{% if legal_host_phone %}Phone: {{ legal_host_phone }}<br/>{% endif %}' },
  { pattern: /ovh\.com\s*<\/p>/g, replacement: '{% if legal_host_website %}{{ legal_host_website }}{% endif %}\n            </p>' },
];

// Welcome words replacement (complex - needs special handling)
const welcomeWordsPattern = /<span class="cd-words-wrapper waiting"><b class="is-visible">super<\/b><b>fucking<\/b><b>french<\/b><b>cool<\/b><\/span>/g;
const welcomeWordsReplacement = `<span class="cd-words-wrapper waiting"><b class="is-visible">{{ welcome_words.split(',')[0] if welcome_words else 'super' }}</b>{% for word in welcome_words.split(',')[1:] %}<b>{{ word }}</b>{% endfor %}</span>`;

function generateTemplate() {
  console.log('Reading source:', SOURCE);

  let content;
  try {
    content = readFileSync(SOURCE, 'utf-8');
  } catch (error) {
    console.error('Error: Could not read', SOURCE);
    console.error('Make sure to run "npm run build" first.');
    process.exit(1);
  }

  // Apply all replacements
  for (const { pattern, replacement } of replacements) {
    content = content.replace(pattern, replacement);
  }

  for (const { pattern, replacement } of policiesSectionReplacements) {
    content = content.replace(pattern, replacement);
  }

  // Apply welcome words replacement
  content = content.replace(welcomeWordsPattern, welcomeWordsReplacement);

  // Ensure target directory exists
  mkdirSync(dirname(TARGET), { recursive: true });

  // Write the template
  writeFileSync(TARGET, content, 'utf-8');
  console.log('Generated template:', TARGET);
}

generateTemplate();
