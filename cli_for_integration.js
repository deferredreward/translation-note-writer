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

// Dynamic import to load the converter module
import(CONVERTER_PATH).then(({ convertGLQuotes2OLQuotes, addGLQuoteCols }) => {
  // Suppress console output during execution
  const originalLog = console.log;
  const originalError = console.error;
  const suppressedLogs = [];

  console.log = (...args) => suppressedLogs.push(args);
  console.error = (...args) => suppressedLogs.push(args);

  const command = process.argv[2];

  if (command === 'gl2ol') {
    // Convert English (GL) to Hebrew/Greek (OL)
    const bibleLink = process.argv[3] || 'unfoldingWord/en_ult/master';
    const bookCode = process.argv[4];
    const tsvContent = process.argv[5];

    convertGLQuotes2OLQuotes({
      bibleLink,
      bookCode,
      tsvContent,
      trySeparatorsAndOccurrences: false,
      quiet: true
    })
      .then(result => {
        console.log = originalLog;
        console.error = originalError;
        originalLog(JSON.stringify(result));
      })
      .catch(error => {
        console.log = originalLog;
        console.error = originalError;
        originalError(JSON.stringify({ error: error.toString() }));
        process.exit(1);
      });

  } else if (command === 'addgl') {
    // Add GL quote columns (converts OL back to GL)
    const bibleLinks = process.argv[3].split(',');
    const bookCode = process.argv[4];
    const tsvContent = process.argv[5];

    addGLQuoteCols({
      bibleLinks,
      bookCode,
      tsvContent,
      trySeparatorsAndOccurrences: false,
      quiet: true
    })
      .then(result => {
        console.log = originalLog;
        console.error = originalError;
        originalLog(JSON.stringify(result));
      })
      .catch(error => {
        console.log = originalLog;
        console.error = originalError;
        originalError(JSON.stringify({ error: error.toString() }));
        process.exit(1);
      });

  } else {
    console.log = originalLog;
    console.error = originalError;
    originalError('Usage: node cli.js [gl2ol|addgl] [args...]');
    process.exit(1);
  }
}).catch(error => {
  console.error(`Error loading converter module from ${CONVERTER_PATH}`);
  console.error('Make sure:');
  console.error('  1. The path in CONVERTER_PATH is correct');
  console.error('  2. You have run "npm run build" in tsv-quote-converters directory');
  console.error(`\nError: ${error.message}`);
  process.exit(1);
});
