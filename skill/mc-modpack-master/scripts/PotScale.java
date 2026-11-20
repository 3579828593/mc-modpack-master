import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import javax.imageio.ImageIO;

/**
 * 把目录树下每张 PNG 的两个维度各自向上取到最近的 2 的幂（最小 16）。
 * 用于修复破坏方块图集 mipmap 的非 2 次幂贴图。
 *
 * 用法: java PotScale <源目录> <输出目录>
 * 注意: 带 .png.mcmeta 的贴图不要放进来源目录——帧尺寸写死在元数据里，改分辨率会破坏帧布局。
 */
public class PotScale {

    static int nextPow2(int v) {
        int p = 16;
        while (p < v) p <<= 1;
        return p;
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.out.println("usage: PotScale <srcDir> <dstDir>");
            return;
        }
        Path src = Paths.get(args[0]);
        Path dst = Paths.get(args[1]);
        final int[] done = {0};
        final int[] skipped = {0};

        Files.walk(src)
             .filter(p -> p.toString().toLowerCase().endsWith(".png"))
             .forEach(p -> {
                 try {
                     BufferedImage in = ImageIO.read(p.toFile());
                     if (in == null) { skipped[0]++; return; }
                     int w = nextPow2(in.getWidth());
                     int h = nextPow2(in.getHeight());
                     if (w == in.getWidth() && h == in.getHeight()) { skipped[0]++; return; }
                     BufferedImage out = new BufferedImage(w, h, BufferedImage.TYPE_INT_ARGB);
                     Graphics2D g = out.createGraphics();
                     g.setRenderingHint(RenderingHints.KEY_INTERPOLATION,
                                        RenderingHints.VALUE_INTERPOLATION_BILINEAR);
                     g.drawImage(in, 0, 0, w, h, null);
                     g.dispose();
                     Path q = dst.resolve(src.relativize(p));
                     Files.createDirectories(q.getParent());
                     ImageIO.write(out, "png", q.toFile());
                     done[0]++;
                 } catch (Exception e) {
                     throw new RuntimeException(e);
                 }
             });

        System.out.println("scaled=" + done[0] + " already_ok=" + skipped[0]);
    }
}
