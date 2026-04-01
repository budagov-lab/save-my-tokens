#!/usr/bin/env python
"""Initialize Neo4j graph database with schema."""

import sys
from pathlib import Path

try:
    from neo4j import GraphDatabase
except ImportError:
    print("❌ neo4j not installed. Run: pip install neo4j")
    sys.exit(1)

# Configuration
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"


def create_schema(driver):
    """Create graph database schema (node labels and relationship types)."""
    with driver.session() as session:
        # Create constraints for uniqueness
        constraints = [
            "CREATE CONSTRAINT file_path IF NOT EXISTS FOR (f:File) REQUIRE f.path IS UNIQUE",
            "CREATE CONSTRAINT function_id IF NOT EXISTS FOR (fn:Function) REQUIRE fn.id IS UNIQUE",
            "CREATE CONSTRAINT class_id IF NOT EXISTS FOR (c:Class) REQUIRE c.id IS UNIQUE",
        ]

        for constraint in constraints:
            try:
                session.run(constraint)
                print(f"✓ {constraint.split('IF NOT EXISTS')[0].strip()}")
            except Exception as e:
                if "already exists" in str(e):
                    print(f"✓ {constraint.split('IF NOT EXISTS')[0].strip()} (already exists)")
                else:
                    print(f"✗ {constraint}: {e}")


def test_connection(uri, user, password):
    """Test connection to Neo4j."""
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session() as session:
            result = session.run("RETURN 'Neo4j is ready!' as message")
            msg = result.single()["message"]
            print(f"✓ {msg}")
        driver.close()
        return True
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False


if __name__ == "__main__":
    print("Initializing Neo4j Graph Database...")
    print(f"Connecting to {NEO4J_URI}...")

    if not test_connection(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD):
        print("\n⚠️ Neo4j not accessible. Start Docker:")
        print("  docker-compose up -d")
        sys.exit(1)

    print("\nCreating schema...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    create_schema(driver)
    driver.close()

    print("\n✓ Neo4j setup complete!")
