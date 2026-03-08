-- ============================================================================
-- MCPHub Database Initialization
-- ============================================================================
-- This file is executed when the PostgreSQL container first starts up
--
-- Purpose:
-- - Enable required PostgreSQL extensions
-- - Set up initial database configuration
-- ============================================================================

-- Enable ltree extension for hierarchical context paths
CREATE EXTENSION IF NOT EXISTS ltree;

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable pgvector for vector embeddings (optional, for future vector storage in PG)
-- Note: Requires pgvector to be installed in the Docker image
-- CREATE EXTENSION IF NOT EXISTS vector;

-- Set timezone to UTC
SET timezone = 'UTC';

-- Log successful initialization
DO $$
BEGIN
  RAISE NOTICE 'MCPHub database initialized successfully';
  RAISE NOTICE 'Extensions enabled: ltree, uuid-ossp';
END $$;
