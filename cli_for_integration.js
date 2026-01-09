#!/usr/bin/env node
/**
 * CLI Bridge for TSV Quote Converters
 *
 * SETUP INSTRUCTIONS:
 * 1. Copy this file to your project directory
 * 2. Update the import path below to point to your tsv-quote-converters installation
 * 3. Make sure tsv-quote-converters has been built: cd tsv-quote-converters && npm run build
 *
 * USAGE:
 * node cli.js gl2ol <bible_link> <book_code> <tsv_content>
 * node cli.js addgl <bible_links> <book_code> <tsv_content>
 */

// UPDATE THIS PATH to point to your tsv-quote-converters directory
// Examples:
//   Same directory: './tsv-quote-converters/dist/tsv-quote-converters.mjs'
//   Parent directory: '../tsv-quote-converters/dist/tsv-quote-converters.mjs'
//   Absolute path: '/home/user/projects/tsv-quote-converters/dist/tsv-quote-converters.mjs'
const CONVERTER_PATH = '../tsv-quote-converters/dist/tsv-quote-converters.mjs';

const fs = require('fs');

// Minimal HTML entity decoding (no DOM dependency)
function decodeEntities(str) {
  if (!str) return str;
  return str
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}

// Preprocess TSV: normalize split quotes and decode entities in Quote column
function preprocessTSVForGLtoOL(tsvContent) {
  if (!tsvContent) return tsvContent;

  const lines = tsvContent.split(/\r?\n/);
  if (lines.length === 0) return tsvContent;

  const header = lines[0];
  const headers = header.split('\t');
  const quoteIdx = headers.indexOf('Quote');

  // If no Quote column, return as-is
  if (quoteIdx === -1) return tsvContent;

  const out = [header];
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    if (!line) { out.push(line); continue; }
    const cols = line.split('\t');
    // Guard if malformed row
    if (cols.length <= quoteIdx) { out.push(line); continue; }

    let q = cols[quoteIdx] || '';
    // Decode entities first
    q = decodeEntities(q);
    // Note: '&' is a valid multi-part separator per integration guide.
    // We only decode entities here; no separator substitution.
    cols[quoteIdx] = q;
    out.push(cols.join('\t'));
  }

  return out.join('\n');
}

// Helper to read TSV content from arg/stdin/file
function getTsvContent(tsvArg) {
  // Read from stdin when '-' is passed
  if (tsvArg === '-') {
    return new Promise((resolve, reject) => {
      try {
        let data = '';
        process.stdin.setEncoding('utf8');
        process.stdin.on('data', chunk => (data += chunk));
        process.stdin.on('end', () => resolve(data));
        process.stdin.resume();
      } catch (e) {
        reject(e);
      }
    });
  }

  // Read from file when '@path' is passed
  if (tsvArg && tsvArg.startsWith('@')) {
    const path = tsvArg.slice(1);
    return Promise.resolve(fs.readFileSync(path, 'utf8'));
  }

  // Raw string argument (existing behavior)
  return Promise.resolve(tsvArg || '');
}

// Dynamic import to load the converter module
import(CONVERTER_PATH).then(({ convertGLQuotes2OLQuotes, addGLQuoteCols }) => {
  // Suppress console output during execution
  const originalLog = console.log;
  const originalError = console.error;
  const suppressedLogs = [];

  console.log = (...args) => suppressedLogs.push(args);
  console.error = (...args) => suppressedLogs.push(args);

  const command = process.argv[2];

  (async () => {
    if (command === 'gl2ol') {
      // Convert English (GL) to Hebrew/Greek (OL)
      const bibleLink = process.argv[3] || 'unfoldingWord/en_ult/master';
      const bookCode = process.argv[4];
      const tsvArg = process.argv[5];
      let tsvContent = await getTsvContent(tsvArg);
      // Normalize split quotes and decode entities in GL Quote column
      tsvContent = preprocessTSVForGLtoOL(tsvContent);

      const result = await convertGLQuotes2OLQuotes({
        bibleLink,
        bookCode,
        tsvContent,
        trySeparatorsAndOccurrences: true,
        quiet: true
      });

      console.log = originalLog;
      console.error = originalError;
      originalLog(JSON.stringify(result));

    } else if (command === 'addgl') {
      // Add GL quote columns (converts OL back to GL)
      const bibleLinks = process.argv[3].split(',');
      const bookCode = process.argv[4];
      const tsvArg = process.argv[5];
      const tsvContent = await getTsvContent(tsvArg);

      const result = await addGLQuoteCols({
        bibleLinks,
        bookCode,
        tsvContent,
        trySeparatorsAndOccurrences: true,
        quiet: true
      });

      console.log = originalLog;
      console.error = originalError;
      originalLog(JSON.stringify(result));

    } else {
      console.log = originalLog;
      console.error = originalError;
      originalError('Usage: node cli.js [gl2ol|addgl] [args...]');
      process.exit(1);
    }
  })().catch(error => {
    console.log = originalLog;
    console.error = originalError;
    originalError(JSON.stringify({ error: error.toString() }));
    process.exit(1);
  });
}).catch(error => {
  console.error(`Error loading converter module from ${CONVERTER_PATH}`);
  console.error('Make sure:');
  console.error('  1. The path in CONVERTER_PATH is correct');
  console.error('  2. You have run "npm run build" in tsv-quote-converters directory');
  console.error(`\nError: ${error.message}`);
  process.exit(1);
});
