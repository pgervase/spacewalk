/**
 * Copyright (c) 2009--2011 Red Hat, Inc.
 *
 * This software is licensed to you under the GNU General Public License,
 * version 2 (GPLv2). There is NO WARRANTY for this software, express or
 * implied, including the implied warranties of MERCHANTABILITY or FITNESS
 * FOR A PARTICULAR PURPOSE. You should have received a copy of GPLv2
 * along with this software; if not, see
 * http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.
 *
 * Red Hat trademarks are not licensed under GPLv2. No permission is
 * granted to use or replicate Red Hat trademarks that are incorporated
 * in this software or its documentation.
 */
package org.cobbler;

import java.util.LinkedList;
import java.util.List;
import java.util.Map;

/**
 * @author paji
 * @version $Rev$
 */
public class Distro extends CobblerObject {
    private static final String KERNEL = "kernel";

    private static final String ARCH = "arch";
    private static final String BREED = "breed";
    private static final String OS_VERSION = "os_version";
    private static final String INITRD = "initrd";
    private static final String SOURCE_REPOS = "source_repos";
    private static final String TREE_BUILD_TIME = "tree_build_time";

    private Distro(CobblerConnection clientIn) {
        client = clientIn;
    }

    /**
     * Create a new distro in cobbler
     * @param client the xmlrpc client
     * @param name the name of the distro
     * @param kernel the kernel path of the distro
     * @param initrd the initrd path of the distro
     * @param ksmeta inital ksmeta to set
     * @param breed initial breed to set
     * @param osVersion initial os_version to set
     * @param arch initial cobbler arch to set
     * @return a new Distro
     */
    public static Distro create(CobblerConnection client, String name, String kernel,
            String initrd, Map ksmeta, String breed, String osVersion, String arch) {
        Distro distro = new Distro(client);
        distro.handle = (String) client.invokeTokenMethod("new_distro");
        distro.modify(NAME, name);
        distro.setKernel(kernel);
        distro.setInitrd(initrd);
        if (ksmeta.containsKey("autoyast")) {
            distro.setBreed("suse");
        }
        else if (breed != null) {
            distro.setBreed(breed);
        }
        if (osVersion != null) {
            distro.setOsVersion(osVersion);
        }
        distro.setKsMeta(ksmeta);
        distro.setArch(arch);
        distro.save();
        distro = lookupByName(client, name);
        return distro;
    }

    /**
     * Returns a distro matching the given name or null
     * @param client the xmlrpc client
     * @param name the distro name
     * @return the distro that maps to the name or null
     */
    public static Distro lookupByName(CobblerConnection client, String name) {
        return handleLookup(client, lookupDataMapByName(client, name, "get_distro"));
    }

    /**
     * Returns a distro matching the given uid or null
     * @param client the xmlrpc client
     * @param id the uid to search for
     * @return the distro matching the UID
     */
    public static Distro lookupById(CobblerConnection client, String id) {
        return handleLookup(client, lookupDataMapById(client,
                                        id, "find_distro"));
    }

    private static Distro handleLookup(CobblerConnection client, Map distroMap) {
        if (distroMap != null) {
            Distro distro = new Distro(client);
            distro.dataMap = distroMap;
            return distro;
        }
        return null;
    }

    /**
     * Returns a list of available Distros
     * @param connection the cobbler connection
     * @return a list of Distros.
     */
    public static List<Distro> list(CobblerConnection connection) {
        List <Distro> distros = new LinkedList<Distro>();
        List <Map<String, Object >> cDistros = (List <Map<String, Object >>)
                                        connection.invokeMethod("get_distros");

        for (Map<String, Object> distroMap : cDistros) {
            Distro distro = new Distro(connection);
            distro.dataMap = distroMap;
            distros.add(distro);
        }
        return distros;
    }

    @Override
    protected String invokeGetHandle() {
        return (String)client.invokeTokenMethod("get_distro_handle", this.getName());
    }

    @Override
    protected void invokeModify(String key, Object value) {
        client.invokeTokenMethod("modify_distro", getHandle(), key, value);
    }

    /**
     * Save the distro
     */
    @Override
    protected void invokeSave() {
        client.invokeTokenMethod("save_distro", getHandle());
    }

    /**
     * Remove the distro
     */
    @Override
    protected boolean invokeRemove() {
        return (Boolean) client.invokeTokenMethod("remove_distro", getName());
    }

    /**
     * Rename the distro
     */
    @Override
    protected void invokeRename(String newNameIn) {
        client.invokeTokenMethod("rename_distro", getHandle(), newNameIn);
    }

    /**
     * Reloads the distro
     */
    @Override
    public void reload() {
        Distro newDistro = lookupById(client, getId());
        dataMap = newDistro.dataMap;
    }

    /**
     * @return the arch
     */
    public String getArch() {
        return (String)dataMap.get(ARCH);
    }


    /**
     * @param archIn the arch to set
     */
    public void setArch(String archIn) {
        modify(ARCH, archIn);
    }

    /**
     * @return the kernelPath
     */
    public String getKernel() {
        return (String)dataMap.get(KERNEL);
    }


    /**
     * @param kernelPathIn the kernelPath to set
     */
    public void setKernel(String kernelPathIn) {
        modify(KERNEL, kernelPathIn);
    }


    /**
     * @return the osVersion
     */
    public String getOsVersion() {
        return (String)dataMap.get(OS_VERSION);
    }


    /**
     * @param osVersionIn the osVersion to set
     */
    public void setOsVersion(String osVersionIn) {
        modify(OS_VERSION, osVersionIn);
    }


    /**
     * @return the initrdPath
     */
    public String getInitrd() {
        return (String)dataMap.get(INITRD);
    }


    /**
     * @param initrdPathIn the initrdPath to set
     */
    public void setInitrd(String initrdPathIn) {
        modify(INITRD, initrdPathIn);
    }


    /**
     * @return the sourceRepos
     */
    public List<String> getSourceRepos() {
        return (List<String>)dataMap.get(SOURCE_REPOS);
    }


    /**
     * @param sourceReposIn the sourceRepos to set
     */
    public void setSourceRepos(List<String> sourceReposIn) {
        modify(SOURCE_REPOS, sourceReposIn);
    }

    /**
     * @return the treeBuildTime
     */
    public long getTreeBuildTime() {
        return (Long)dataMap.get(TREE_BUILD_TIME);
    }


    /**
     * @param treeBuildTimeIn the treeBuildTime to set
     */
    public void setTreeBuildTime(long treeBuildTimeIn) {
        modify(TREE_BUILD_TIME, treeBuildTimeIn);
    }

    /**
     * @return the breed
     */
    public String getBreed() {
        return (String)dataMap.get(BREED);
    }


    /**
     * @param breedIn the breed to set
     */
    public void setBreed(String breedIn) {
        modify(BREED, breedIn);
    }
}
