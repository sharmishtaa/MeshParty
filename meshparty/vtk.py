import vtk
from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray
import numpy as np


def numpy_rep_to_vtk(vertices, shapes):
    """ converts a numpy representation of vertices and vertex connection graph
      to a polydata object and corresponding cell array

        :param vertices: a Nx3 numpy array of vertex locations
        :param shapes: a MxK numpy array of vertex connectivity
                       (could be triangles (K=3) or edges (K=2))

        :return: (vtkPolyData, vtkCellArray)
        a polydata object with point set according to vertices,
        and a vtkCellArray of the shapes
    """

    ndim = shapes.shape[1]

    mesh = vtk.vtkPolyData()
    points = vtk.vtkPoints()
    points.SetData(numpy_to_vtk(vertices, deep=1))
    mesh.SetPoints(points)

    cells = vtk.vtkCellArray()

    # Seemingly, VTK may be compiled as 32 bit or 64 bit.
    # We need to make sure that we convert the trilist to the correct dtype
    # based on this. See numpy_to_vtkIdTypeArray() for details.
    isize = vtk.vtkIdTypeArray().GetDataTypeSize()
    req_dtype = np.int32 if isize == 4 else np.int64
    n_tris = shapes.shape[0]
    cells.SetCells(n_tris,
                   numpy_to_vtkIdTypeArray(
                       np.hstack((np.ones(n_tris)[:, None] * ndim,
                                  shapes)).astype(req_dtype).ravel(),
                       deep=1))

    return mesh, cells


def graph_to_vtk(vertices, edges):
    """ converts a numpy representation of vertices and edges
      to a vtkPolyData object

        :param vertices: a Nx3 numpy array of vertex locations
        :param eges: a Mx2 numpy array of vertex connectivity
        where the values are the indexes of connected vertices

        :return: vtkPolyData
        a polydata object with point set according to vertices
        and edges as its Lines

        :raises: ValueError
        if edges is not 2d or refers to out of bounds vertices
    """
    if edges.shape[1] != 2:
        raise ValueError('graph_to_vtk() only works on edge lists')
    if np.max(edges) >= len(vertices):
        msg = 'edges refer to non existent vertices {}.'
        raise ValueError(msg.format(np.max(edges)))
    mesh, cells = numpy_rep_to_vtk(vertices, edges)
    mesh.SetLines(cells)
    return mesh


def trimesh_to_vtk(vertices, tris):
    """Return a `vtkPolyData` representation of a :map:`TriMesh` instance
    Parameters
    ----------
    vertices : numpy array of Nx3 vertex positions (x,y,z)
    tris: numpy array of Mx3 triangle vertex indices (int64)
    Returns
    -------
    `vtk_mesh` : `vtkPolyData`
        A VTK mesh representation of the Menpo :map:`TriMesh` data
    Raises
    ------
    ValueError:
        If the input trimesh is not 3D
        or tris refers to out of bounds vertex indices
    """

    if tris.shape[1] != 3:
        raise ValueError('trimesh_to_vtk() only works on 3D TriMesh instances')
    if np.max(tris) >= len(vertices):
        msg = 'edges refer to non existent vertices {}.'
        raise ValueError(msg.format(np.max(tris)))
    mesh, cells = numpy_rep_to_vtk(vertices, tris)
    mesh.SetPolys(cells)

    return mesh


def calculate_cross_sections(mesh, graph_verts, graph_edges):
  
    mesh_polydata = trimesh_to_vtk(mesh.vertices, mesh.faces)

    cutter = vtk.vtkPlaneCutter()
    cutter.SetInputData(mesh_polydata)
    plane = vtk.vtkPlane()
    cd = vtk.vtkCleanPolyData()
    cf = vtk.vtkPolyDataConnectivityFilter()
    cf.SetInputConnection(cd.GetOutputPort())
    cf.SetExtractionModeToClosestPointRegion()
    cutter.SetPlane(plane)
    cutStrips = vtk.vtkStripper()
    cutStrips.JoinContiguousSegmentsOn()
    cutStrips.SetInputConnection(cf.GetOutputPort())

    cross_sections = np.zeros(len(graph_edges), dtype=np.float)
    massfilter = vtk.vtkMassProperties()
    massfilter.SetInputConnection(cutter.GetOutputPort())
    t = vtk.vtkTriangleFilter()
    dvs = graph_verts[graph_edges[:, 0], :]-graph_verts[graph_edges[:, 1], :]
    dvs = (dvs / np.linalg.norm(dvs, axis=1)[:, np.newaxis])
    for k, edge in enumerate(graph_edges):
        dv = dvs[k, :]

        dv = dv.tolist()

        v = graph_verts[graph_edges[k, 0], :]
        v = v.tolist()
        plane.SetNormal(*dv)
        plane.SetOrigin(*v)

        cutter.Update()
        pd = cutter.GetOutputDataObject(0).GetBlock(0).GetPiece(0)

        cd.SetInputData(pd)
        cf.SetClosestPoint(*v)
        cutStrips.Update()

        cutPoly = vtk.vtkPolyData()
        cutPoly.SetPoints(cutStrips.GetOutput().GetPoints())
        cutPoly.SetPolys(cutStrips.GetOutput().GetLines())

        t.SetInputData(cutPoly)

        massfilter = vtk.vtkMassProperties()
        massfilter.SetInputConnection(t.GetOutputPort())
        massfilter.Update()

        cross_sections[k] = massfilter.GetSurfaceArea()

    return cross_sections
