"""Serveur MCP testé via des flux en mémoire (client officiel)."""

import anyio
import pytest

from conftest import requires_bpy

pytestmark = requires_bpy


async def _session(engine, fn):
    from mcp.client.session import ClientSession
    from mcp.shared.memory import create_client_server_memory_streams

    from blender_buildings.mcp_server import create_server

    server = create_server(engine)
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        async with anyio.create_task_group() as tg:
            tg.start_soon(lambda: server._lowlevel_server.run(server_streams[0], server_streams[1], server._lowlevel_server.create_initialization_options()))
            async with ClientSession(*client_streams) as s:
                await s.initialize()
                await fn(s)
            tg.cancel_scope.cancel()


def run(engine, fn):
    anyio.run(lambda: _session(engine, fn))


def test_tools_resources_prompts_listed(engine):
    async def fn(s):
        tools = {t.name for t in (await s.list_tools()).tools}
        assert {"build_building", "render_preview", "export_model", "compute_building_metrics", "run_blender_python"} <= tools
        uris = {str(r.uri) for r in (await s.list_resources()).resources}
        assert "presets://list" in uris
        prompts = {p.name for p in (await s.list_prompts()).prompts}
        assert "design_building" in prompts

    run(engine, fn)


def test_build_metrics_render_export(engine, out_dir):
    async def fn(s):
        r = await s.call_tool("build_building", {"preset": "haussmann", "overrides": {"floors": 7}})
        assert not r.is_error and r.structured_content["metrics"]["floors"] == 7
        r = await s.call_tool("compute_building_metrics", {"preset": "hotel", "overrides": {"site.parcel_area": 1000}})
        assert r.structured_content["metrics"]["site_coverage_ratio"] > 0
        r = await s.call_tool("render_preview", {"engine": "workbench", "width": 160, "height": 100, "view": "front"})
        assert not r.is_error
        assert r.content[0].type == "image" and r.content[0].mime_type == "image/png" and len(r.content[0].data) > 100
        r = await s.call_tool("export_model", {"format": "glb"})
        assert r.structured_content["size_bytes"] > 1000 and str(out_dir) in r.structured_content["path"]
        r = await s.call_tool("scene_info", {})
        assert r.structured_content["object_count"] >= 1

    run(engine, fn)


def test_street_and_block(engine):
    async def fn(s):
        r = await s.call_tool("build_street", {"preset": "office", "count": 2, "seed": 3})
        assert len(r.structured_content["buildings"]) == 2
        r = await s.call_tool("build_block", {"buildings": [{"preset": "house", "overrides": {"position": [0, 0, 0]}}, {"preset": "house", "overrides": {"position": [20, 0, 0]}}]})
        assert len(r.structured_content["buildings"]) == 2

    run(engine, fn)


def test_errors_are_readable(engine):
    async def fn(s):
        r = await s.call_tool("build_building", {"preset": "nope"})
        assert r.is_error and "Preset inconnu" in r.content[0].text
        r = await s.call_tool("build_building", {"spec": {"floors": 0}})
        assert r.is_error and "floors" in r.content[0].text

    run(engine, fn)


def test_resources_and_prompt(engine):
    async def fn(s):
        rr = await s.read_resource("presets://office")
        assert '"use": "office"' in rr.contents[0].text
        rr = await s.read_resource("spec://schema")
        assert "footprint" in rr.contents[0].text
        p = await s.get_prompt("design_building", {"brief": "R+6 à Lyon"})
        assert "R+6 à Lyon" in p.messages[0].content.text

    run(engine, fn)


def test_python_tool_can_be_disabled(engine, monkeypatch):
    monkeypatch.setenv("BLENDER_BUILDINGS_ALLOW_PYTHON", "0")

    async def fn(s):
        tools = {t.name for t in (await s.list_tools()).tools}
        assert "run_blender_python" not in tools

    run(engine, fn)
